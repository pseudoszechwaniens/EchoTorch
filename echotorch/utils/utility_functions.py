# -*- coding: utf-8 -*-
#
# File : echotorch/utils/utility_functions.py
# Description : Utility functions
# Date : 23th of February, 2021
#
# This file is part of EchoTorch.  EchoTorch is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Nils Schaetti <nils.schaetti@unine.ch>

# Imports
import torch
import numpy as np
from .error_measures import nrmse, generalized_squared_cosine
from scipy.interpolate import interp1d
import numpy.linalg as lin
from scipy import stats
import scipy.integrate as integrate
import matplotlib.pyplot as plt


# Compute entropy per variable
def entropy(x):
    """
    Compute entropy per variable
    :param x: Samples (batch size, n. samples, n. variables) or (n. samples, n. variables)
    :return: A tensor (n. variables) containing measured entropy
    """
    # Resize if batch is there
    if x.ndim == 3:
        batch_size = x.size(0)
        time_length = x.size(1)
        x = x.reshape(batch_size * time_length, x.size(2))
    # end if

    # Number of variables
    n_vars = x.size(1)

    # Tensor for each variable
    entropy_tensor = torch.zeros(n_vars)

    # Estimate kernels for each variables
    for var_i in range(n_vars):
        entropy_tensor[var_i] = integrate.quad(stats.gaussian_kde(x), -1, 1)
    # end for

    return entropy_tensor
# end entropy


# Compute the rank of a matrix
def rank(m, tol=1e-14):
    """
    Compute the rank of a matrix
    :param m: Matrix
    """
    # SVD on M
    Um, Sm, _ = torch.svd(m)

    # How many sv above threshold
    return int(torch.sum(1.0 * (Sm > tol)))
# end rank


# Compute quota of a conceptor matrix
def quota(conceptor_matrix):
    """
    Compute quota of a conceptor matrix
    """
    _, Se, _ = torch.svd(conceptor_matrix)
    return float(torch.sum(Se).item() / conceptor_matrix.size(0))
# end quota


# Compute correlation matrix
def compute_correlation_matrix(states):
    """
    Compute correlation matrix
    :param states:
    :return:
    """
    return states.t().mm(states) / float(states.size(0))
# end compute_correlation_matrix


# Align pattern
def align_pattern(interpolation_rate, truth_pattern, generated_pattern):
    """
    Align pattern
    :param interpolation_rate:
    :param truth_pattern:
    :param generated_pattern:
    :return:
    """
    # Length
    truth_length = truth_pattern.size(0)
    generated_length = generated_pattern.size(0)

    # Remove useless dimension
    truth_pattern = truth_pattern.view(-1)
    generated_pattern = generated_pattern.view(-1)

    # Quadratic interpolation functions
    truth_pattern_func = interp1d(np.arange(truth_length), truth_pattern.numpy(), kind='quadratic')
    generated_pattern_func = interp1d(np.arange(generated_length), generated_pattern.numpy(), kind='quadratic')

    # Get interpolated patterns
    truth_pattern_int = truth_pattern_func(np.arange(0, truth_length - 1.0, 1.0 / interpolation_rate))
    generated_pattern_int = generated_pattern_func(np.arange(0, generated_length - 1.0, 1.0 / interpolation_rate))

    # Generated interpolated pattern length
    L = generated_pattern_int.shape[0]

    # Truth interpolated pattern length
    M = truth_pattern_int.shape[0]

    # Save L2 distance for each phase shift
    phase_matches = np.zeros(L - M)

    # For each phase shift
    for phases_hift in range(L - M):
        phase_matches[phases_hift] = lin.norm(truth_pattern_int - generated_pattern_int[phases_hift:phases_hift + M])
    # end for

    # Best match
    max_ind = int(np.argmax(-phase_matches))

    # Get the position in the original signal
    coarse_max_ind = int(np.ceil(max_ind / interpolation_rate))

    # Get the generated output matching the original signal
    generated_aligned = generated_pattern_int[
        np.arange(max_ind, max_ind + interpolation_rate * truth_length, interpolation_rate)
    ]

    return max_ind, coarse_max_ind, torch.from_numpy(generated_aligned).view(-1, 1)
# end align_pattern


# Pattern interpolation
def pattern_interpolation(p, y, interpolation_rate, error_measure=nrmse):
    """
    Pattern interpolation
    :param p:
    :param y:
    :param interpolation_rate:
    :param error_measure:
    :return:
    """
    # Length
    CL = y.size(0)
    PL = p.size(0)

    # Interpolation of generated sample
    interpolated_func = interp1d(np.arange(CL), y[:, 0].numpy(), kind='quadratic')
    interpolated_generated = interpolated_func(np.arange(0, CL - 1.0, 1.0 / interpolation_rate))

    # Interpolation of target sample
    interpolated_func = interp1d(np.arange(PL), p.numpy(), kind='quadratic')
    interpolated_pattern = interpolated_func(np.arange(0, PL - 1.0, 1.0 / interpolation_rate))

    # Length of generated (interpolated)
    L = interpolated_generated.shape[0]

    # Length of original (interpolated)
    M = interpolated_pattern.shape[0]

    # Save norm-2 for each phase shift
    norm_phase_shift = np.zeros(L - M)

    # Phase shift
    for shift in range(L - M):
        # Norm-2 between generated an original
        norm_phase_shift[shift] = lin.norm(interpolated_generated[shift:shift + M] - interpolated_pattern)
    # end for

    # Find minimum distance
    min_norm = int(np.argmax(-norm_phase_shift))

    # Generated signal aligned
    generated_sample_aligned = interpolated_generated[
        np.arange(min_norm, min_norm + PL * interpolation_rate, interpolation_rate)
    ]

    # Original phase
    original_phase = np.ceil(min_norm / interpolation_rate)

    # To Tensor
    generated_sample_aligned = torch.Tensor(generated_sample_aligned)

    # Double ?
    if isinstance(generated_sample_aligned, torch.DoubleTensor):
        generated_sample_aligned = generated_sample_aligned.double()
    # end if

    # Error after alignment
    error_aligned = error_measure(generated_sample_aligned.reshape(1, -1), p.reshape(1, -1))

    return generated_sample_aligned, original_phase, error_aligned
# end find_phase_shift


# Find best pattern interpolation
def find_pattern_interpolation(p, y, interpolation_rate, n_matches, error_measure=nrmse):
    """
    Pattern interpolation
    :param p:
    :param y:
    :param interpolation_rate:
    :param error_measure:
    :return:
    """
    # Length
    CL = y.size(0)
    PL = p.size(0)

    # Interpolation of generated sample
    interpolated_func = interp1d(np.arange(CL), y[:, 0].numpy(), kind='quadratic')
    interpolated_generated = interpolated_func(np.arange(0, CL - 1.0, 1.0 / interpolation_rate))

    # Interpolation of target sample
    interpolated_func = interp1d(np.arange(PL), p.numpy(), kind='quadratic')
    interpolated_pattern = interpolated_func(np.arange(0, PL - 1.0, 1.0 / interpolation_rate))

    # Length of generated (interpolated)
    L = interpolated_generated.shape[0]

    # Length of original (interpolated)
    M = interpolated_pattern.shape[0]

    # List of best matches
    best_matches = list()

    # Save norm-2 for each phase shift
    norm_phase_shift = np.zeros(L - M)

    # Phase shift
    for shift in range(L - M):
        # Norm-2 between generated an original
        norm_phase_shift[shift] = lin.norm(interpolated_generated[shift:shift + M] - interpolated_pattern)
        best_matches.append((norm_phase_shift[shift], shift))
    # end for

    # Sort by distance
    best_matches = sorted(best_matches, key=lambda tup: tup[0])

    # List of original phase and their norm
    best_phases = list()
    phase_norms = list()

    # Count for average
    norms_add = 0.0
    norms_count = 0

    # For each matches
    for (m_norm, m_pos) in best_matches:
        # Generated signal aligned
        generated_sample_aligned = interpolated_generated[
            np.arange(m_pos, m_pos + PL * interpolation_rate, interpolation_rate)
        ]

        # Original phase
        original_phase = np.ceil(m_pos / interpolation_rate)

        # Add
        best_phases.append(original_phase)

        # To Tensor
        generated_sample_aligned = torch.Tensor(generated_sample_aligned)

        # Double ?
        if isinstance(generated_sample_aligned, torch.DoubleTensor):
            generated_sample_aligned = generated_sample_aligned.double()
        # end if

        # Error after alignment
        error_aligned = error_measure(generated_sample_aligned.reshape(1, -1), p.reshape(1, -1))
        phase_norms.append(error_aligned)
        norms_add += error_aligned
        norms_count += 1
    # end for

    return best_phases, phase_norms, norms_add / norms_count
# end find_pattern_interpolation

# Find best pattern interpolation with threshold
def find_pattern_interpolation_threshold(p, y, interpolation_rate, threshold, error_measure=nrmse):
    """
    Pattern interpolation
    :param p:
    :param y:
    :param interpolation_rate:
    :param error_measure:
    :return:
    """
    # Length
    CL = y.size(0)
    PL = p.size(0)

    # Interpolation of generated sample
    interpolated_func = interp1d(np.arange(CL), y[:, 0].numpy(), kind='quadratic')
    interpolated_generated = interpolated_func(np.arange(0, CL - 1.0, 1.0 / interpolation_rate))

    # Interpolation of target sample
    interpolated_func = interp1d(np.arange(PL), p.numpy(), kind='quadratic')
    interpolated_pattern = interpolated_func(np.arange(0, PL - 1.0, 1.0 / interpolation_rate))

    # Length of generated (interpolated)
    L = interpolated_generated.shape[0]

    # Length of original (interpolated)
    M = interpolated_pattern.shape[0]

    # List of best matches
    matches = list()

    # Save norm-2 for each phase shift
    norm_phase_shift = np.zeros(L - M)

    # Phase shift
    for shift in range(L - M):
        # Norm-2 between generated an original
        norm_phase_shift[shift] = lin.norm(interpolated_generated[shift:shift + M] - interpolated_pattern)
        if norm_phase_shift[shift] < threshold:
            matches.append((shift, norm_phase_shift[shift]))
        # end if
    # end for

    # List of original phase and their norm
    threshold_phases = list()
    threshold_norms = list()

    # Average
    norms_add = 0.0
    norms_count = 1

    # For each matches
    for (m_pos, n_norm) in matches:
        # Generated signal aligned
        generated_sample_aligned = interpolated_generated[
            np.arange(m_pos, m_pos + PL * interpolation_rate, interpolation_rate)
        ]

        # Original phase
        original_phase = np.ceil(m_pos / interpolation_rate)

        # Add
        threshold_phases.append(original_phase)

        # To Tensor
        generated_sample_aligned = torch.Tensor(generated_sample_aligned)

        # Double ?
        if isinstance(generated_sample_aligned, torch.DoubleTensor):
            generated_sample_aligned = generated_sample_aligned.double()
        # end if

        # Error after alignment
        error_aligned = error_measure(generated_sample_aligned.reshape(1, -1), p.reshape(1, -1))
        threshold_norms.append(error_aligned)

        # Average
        norms_add += error_aligned
        norms_count += 1
    # end for

    return threshold_phases, threshold_norms, norms_add / norms_count, norm_phase_shift
# end find_pattern_interpolation_threshold


# Compute similarity matrix
def compute_similarity_matrix(svd_list):
    """
    Compute similarity matrix
    :param svd_list:
    :return:
    """
    # N samples
    n_samples = len(svd_list)

    # Similarity matrix
    sim_matrix = torch.zeros(n_samples, n_samples)

    # For each combinasion
    for i, (Sa, Ua) in enumerate(svd_list):
        for j, (Sb, Ub) in enumerate(svd_list):
            sim_matrix[i, j] = generalized_squared_cosine(Sa, Ua, Sb, Ub)
        # end for
    # end for

    return sim_matrix
# end compute_similarity_matrix


# Compute singular values
def compute_singular_values(stats):
    """
    Compute singular values
    :param states:
    :return:
    """
    # Compute R (correlation matrix)
    R = stats.t().mm(stats) / stats.shape[0]

    # Compute singular values
    return torch.svd(R)
# end compute_singular_values


# Compute spectral radius of a square 2-D tensor
def spectral_radius(m):
    """
    Compute spectral radius of a square 2-D tensor
    :param m: squared 2D tensor
    :return:
    """
    return torch.max(torch.abs(torch.eig(m)[0])).item()
# end spectral_radius


# Compute spectral radius of a square 2-D tensor for stacked-ESN
def deep_spectral_radius(m, leaky_rate):
    """
    Compute spectral radius of a square 2-D tensor for stacked-ESN
    :param m: squared 2D tensor
    :param leaky_rate: Layer's leaky rate
    :return:
    """
    return spectral_radius((1.0 - leaky_rate) * torch.eye(m.size(0), m.size(0)) + leaky_rate * m)
# end spectral_radius


# Normalize a tensor on a single dimension
def normalize(tensor, dim=1):
    """
    Normalize a tensor on a single dimension
    :param t:
    :return:
    """
    pass
# end normalize


# Average probabilties through time
def average_prob(tensor, dim=0):
    """
    Average probabilities through time
    :param tensor:
    :param dim:
    :return:
    """
    return torch.mean(tensor, dim=dim)
# end average_prob


# Max average through time
def max_average_through_time(tensor, dim=0):
    """
    Max average through time
    :param tensor:
    :param dim: Time dimension
    :return:
    """
    average = torch.mean(tensor, dim=dim)
    return torch.max(average, dim=dim)[1]
# end max_average_through_time


# Compute covariance for a  lag
def cov(x, y):
    """
    Compute covariance for a lag
    :param x: Timeseries tensor
    :param y: Timeseries tensor
    :return: The covariance coefficients
    """
    # Average x and y
    x_mu = torch.mean(x, dim=0)
    y_mu = torch.mean(y, dim=0)

    # Average covariance over length
    return torch.mean(torch.mul(x - x_mu, y - y_mu))
# end cov


# AutoCorrelation coefficients function for a time series
def autocorrelation_function(x: torch.Tensor, n_lags: int):
    """
    AutoCorrelation coefficients function for a time series
    @param x: The 1-D timeseries
    @param n_lags: Number of lags
    @return: A 1-D tensor with n_lags+1 components
    """
    # Store coefs
    autocov_coefs = torch.zeros(n_lags+1)

    # Time length for comparison
    com_time_length = x.size(0) - n_lags

    # The time length for comparison must
    # be superior (or equal) to the number of lags required
    if com_time_length < n_lags:
        raise ValueError(
            "Time time length for comparison must "
            "be superior (or equal) to the number of lags required (series of length "
            "{}, {} lags, comparison length of {})".format(x.size(0), n_lags, com_time_length)
        )
    # end if

    # Covariance t to t
    autocov_coefs[0] = cov(x[:com_time_length], x[:com_time_length])

    # For each lag
    for lag_i in range(1, n_lags+1):
        autocov_coefs[lag_i] = cov(
            x[:com_time_length],
            x[lag_i:lag_i + com_time_length]
        )
    # end for

    # Co
    c0 = autocov_coefs[0].item()

    # Normalize with first coef
    autocov_coefs /= c0

    return autocov_coefs
# end autocorrelation_function


# AutoCorrelation Coefficients for a time series
def autocorrelation_coefs(x: torch.Tensor, n_coefs: int):
    """
    AutoCorrelation Coefficients for a time series
    @param x: A 2D tensor (no batch) or 3D tensor (with batch)
    @param n_coefs: Number of coefficients for each dimension
    @return: A 2D tensor (n. channels x n. coefs) if no batch, 3D tensor (n. batch x n.channels x n. coefs) if batched
    """
    # Has batch?
    use_batch = x.ndim == 3

    # Add batch dim if necessary
    if not use_batch:
        x = torch.unsqueeze(x, dim=0)
    # end if

    # Sizes
    batch_size, time_length, n_channels = x.size()

    # Result collector
    result_collector = torch.zeros(batch_size, n_channels, n_coefs+1)

    # For each batch
    for batch_i in range(batch_size):
        # For each channel
        for channel_i in range(n_channels):
            result_collector[batch_i, channel_i] = autocorrelation_function(x[batch_i, :, channel_i], n_lags=n_coefs)
        # end for
    # end for

    # Return result
    if not use_batch:
        return torch.squeeze(result_collector, dim=0)
    # end if
    return result_collector
# end autocorrelation_coefs



