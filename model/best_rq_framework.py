import random

import torch
from torch import nn
from torchvision.transforms import Normalize

from model.best_rq_config import BestRqConfig
from model.random_projection_quanzier import RandomProjectionQuantizer


class BestRqFramework(nn.Module):
    def __init__(self, config: BestRqConfig, encoder: nn.Module):
        super().__init__()
        self.K = config.num_temporal_dimension_reduction_steps
        self.input_norm = Normalize(mean=0, std=1)
        self.random_projection_quantizer = RandomProjectionQuantizer(config)
        self.encoder = encoder
        self.config = config
        self.out_linear = nn.Linear(config.encoder_hidden_size, config.code_book_size)

    def forward(self, input_values: torch.Tensor, input_lengths: torch.Tensor):
        """
        Args:
            input_values (torch.Tensor): with shape `(B, T, D)`
            input_lengths (torch.Tensor): with shape `(B)`

        Returns:

        """
        batch_size, num_steps, hidden_size = input_values.size()

        if not num_steps % self.config.num_temporal_dimension_reduction_steps == 0:
            transformed_num_steps = (num_steps // self.K + 1) * self.K
            padding = torch.zeros(
                batch_size, transformed_num_steps - num_steps, hidden_size, device=input_values.device
            )
            input_values = torch.cat([input_values, padding], dim=1)

        # Reshape to number of encoder out steps
        input_values = input_values.view(batch_size, -1, self.K * hidden_size)
        quantized_input_lengths = input_lengths // (num_steps / self.K) - 1

        masked_input_values, time_mask_indices = self.masking(input_values, quantized_input_lengths)
        masked_input_values = masked_input_values.view(batch_size, num_steps, hidden_size)

        labels = self.random_projection_quantizer(self.input_norm(input_values), time_mask_indices)

        encoder_out = self.encoder(masked_input_values, input_lengths)

        targets = encoder_out[time_mask_indices]
        targets_out = self.out_linear(targets)

        return targets_out, labels

    def masking(self, input_values: torch.Tensor, input_lengths: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            input_values (torch.Tensor): with shape `(B, L, D)`
            input_lengths (torch.Tensor): with shape `(B)'

        Returns:
            tuple(
            torch.Tensor with shape `(B, L, D)`
            torch.Tensor with shape `(B, L)`
            )
        """
        batch_size, num_steps, hidden_size = input_values.size()

        # non mask: 0, maks: 1
        time_mask_indices = torch.zeros(batch_size, num_steps, device=input_values.device, dtype=torch.bool)
        num_masks = 0

        for batch in range(batch_size):
            time_mask_idx_candidates = list(range(int(input_lengths[batch])))
            k = int(self.config.mask_probs * input_lengths[batch])
            num_masks += k
            time_mask_idx_array = torch.tensor(random.sample(time_mask_idx_candidates, k=k), device=input_values.device)

            time_mask_indices[batch, time_mask_idx_array] = 1

        # Replace to random value where mask
        random_values = torch.normal(mean=0, std=0.1, size=(num_masks, hidden_size))
        input_values[time_mask_indices == 1] = random_values

        return input_values, time_mask_indices
