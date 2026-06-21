from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class PhysicsConfig:
    q: float = 1.602e-19
    kb: float = 1.38e-23
    T: float = 300.0
    n: float = 1.4
    m: float = 2.4

    @property
    def A(self) -> float:
        return self.q / (self.kb * self.T)

    @property
    def v_th(self) -> float:
        return self.kb * self.T / self.q


@dataclass
class FittingConfig:
    neg_voltage_threshold: float = -0.2
    pos_voltage_threshold: float = 0.1
    voltage_zero_atol: float = 1e-12
    current_noise_floor: float = 1e-11
    boundary_relative_tol: float = 1e-3
    core_window_low: float = -0.5
    core_window_high: float = 0.3
    core_window_min_points: int = 25
    core_fit_good_mean_error: float = 5.0
    core_fit_good_max_error: float = 30.0
    post_model_trigger_mean_error: float = 8.0
    post_model_trigger_max_error: float = 25.0
    post_model_min_bic_improvement: float = 6.0


@dataclass
class OptimizationConfig:
    multistart_points: int = 10
    method: str = "multistart"
    use_log_parameters: bool = True
    initialization_method: str = "hybrid"
    least_squares_loss: str = "linear"
    loss_f_scale: float = 1.0
    staged_fallback: bool = True
    use_de_fallback: bool = False
    de_maxiter: int = 35
    de_popsize: int = 8
    de_tol: float = 0.02
    de_recombination: float = 0.7
    de_mutation: tuple[float, float] = (0.5, 1.0)
    de_trigger_mean_error: float = 6.0
    de_trigger_max_error: float = 15.0
    target_rel_error: float = 3.0
    target_max_error: float = 5.0
    max_attempts: int = 5
    max_retries: int = 2
    min_retry_improvement: float = 0.01
    random_seed: int = 12345


@dataclass
class RegularizationConfig:
    lambda_: float = 0.0
    prior: np.ndarray = field(default_factory=lambda: np.zeros(4, dtype=float))


@dataclass
class ParallelConfig:
    use: bool = False
    pool_size: int | None = None


@dataclass
class Config:
    physics: PhysicsConfig = field(default_factory=PhysicsConfig)
    fitting: FittingConfig = field(default_factory=FittingConfig)
    optimization: OptimizationConfig = field(default_factory=OptimizationConfig)
    regularization: RegularizationConfig = field(default_factory=RegularizationConfig)
    parallel: ParallelConfig = field(default_factory=ParallelConfig)


def load_config() -> Config:
    return Config()
