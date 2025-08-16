# EVOLVE-BLOCK-START
"""Function minimization example for OpenEvolve"""
import numpy as np


def search_algorithm(iterations=1000, bounds=(-5, 5)):
    """
    Simulated annealing algorithm for global optimization.
    Incorporates temperature-based probability to escape local minima.

    Args:
        iterations: Number of iterations to run
        bounds: Bounds for the search space (min, max)

    Returns:
        Tuple of (best_x, best_y, best_value)
    """
    # Combined grid and random sampling for better initialization
    grid_size = 10
    x_grid = np.linspace(bounds[0], bounds[1], grid_size)
    y_grid = np.linspace(bounds[0], bounds[1], grid_size)
    
    best_value = float('inf')
    for x in x_grid:
        for y in y_grid:
            value = evaluate_function(x, y)
            if value < best_value:
                best_value = value
                best_x, best_y = x, y
    
    # Add random samples to avoid grid bias
    num_starts = 10
    for _ in range(num_starts):
        x = np.random.uniform(bounds[0], bounds[1])
        y = np.random.uniform(bounds[0], bounds[1])
        value = evaluate_function(x, y)
        if value < best_value:
            best_value = value
            best_x, best_y = x, y
    
    current_x, current_y = best_x, best_y
    current_value = best_value
    
    # Initial temperature and cooling rate
    # Higher initial temperature for better global exploration
    temperature = 10.0
    # Slower cooling rate for better convergence
    cooling_rate = 0.999
    
    for i in range(iterations):
        # Generate new candidate with adaptive step size and momentum
        step_size = temperature * (bounds[1] - bounds[0]) / 10
        x = current_x + step_size * np.random.normal() + 0.1 * (best_x - current_x)
        y = current_y + step_size * np.random.normal() + 0.1 * (best_y - current_y)
        
        # Ensure candidate stays within bounds
        x = np.clip(x, bounds[0], bounds[1])
        y = np.clip(y, bounds[0], bounds[1])
        
        value = evaluate_function(x, y)
        
        # Always accept better solutions
        if value < current_value:
            current_x, current_y = x, y
            current_value = value
            if value < best_value:
                best_x, best_y = x, y
                best_value = value
        else:
            # Accept worse solutions with probability based on temperature
            delta = value - current_value
            accept_prob = np.exp(-delta / temperature)
            if np.random.rand() < accept_prob:
                current_x, current_y = x, y
                current_value = value
        
        # Cool down the temperature
        temperature *= cooling_rate
        
        # Add periodic large jumps to explore new regions
        if i % 100 == 0:
            jump_x = np.random.uniform(bounds[0], bounds[1])
            jump_y = np.random.uniform(bounds[0], bounds[1])
            jump_value = evaluate_function(jump_x, jump_y)
            if jump_value < best_value:
                best_value = jump_value
                best_x, best_y = jump_x, jump_y
                current_x, current_y = jump_x, jump_y
                current_value = jump_value

    # Local search refinement with adaptive step size
    step_size = 0.1
    min_step = 1e-6
    while step_size > min_step:
        improved = False
        for dx in [-step_size, 0, step_size]:
            for dy in [-step_size, 0, step_size]:
                x = best_x + dx
                y = best_y + dy
                value = evaluate_function(x, y)
                if value < best_value:
                    best_value = value
                    best_x, best_y = x, y
                    improved = True
        
        # Reduce step size more aggressively if no improvement
        step_size *= 0.5 if improved else 0.1
    
    return best_x, best_y, best_value


# EVOLVE-BLOCK-END


# This part remains fixed (not evolved)
def evaluate_function(x, y):
    """The complex function we're trying to minimize"""
    return np.sin(x) * np.cos(y) + np.sin(x * y) + (x**2 + y**2) / 20


def run_search():
    x, y, value = search_algorithm()
    return x, y, value


if __name__ == "__main__":
    x, y, value = run_search()
    print(f"Found minimum at ({x}, {y}) with value {value}")
