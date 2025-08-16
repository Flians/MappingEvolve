# EVOLVE-BLOCK-START
"""Function minimization example for OpenEvolve"""
import numpy as np


def search_algorithm(iterations=1000, bounds=(-5, 5)):
    """
    An improved search algorithm using simulated annealing and adaptive steps
    to better handle functions with many local minima.

    Args:
        iterations: Number of iterations to run
        bounds: Bounds for the search space (min, max)

    Returns:
        Tuple of (best_x, best_y, best_value)
    """
    # Initialize with grid search for better starting point
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
    
    # Initialize current position
    current_x, current_y = best_x, best_y
    current_value = best_value
    
    # Initialize temperature for simulated annealing
    temperature = 1.0
    cooling_rate = 0.99
    
    # Initialize step size and momentum
    step_size = (bounds[1] - bounds[0]) / 10
    momentum_x, momentum_y = 0, 0
    momentum_factor = 0.9

    for i in range(iterations):
        # Calculate adaptive step size based on progress
        step_size *= 0.99
        
        # Generate new candidate with momentum
        new_x = current_x + step_size * np.random.normal() + momentum_x
        new_y = current_y + step_size * np.random.normal() + momentum_y
        
        # Keep within bounds
        new_x = np.clip(new_x, bounds[0], bounds[1])
        new_y = np.clip(new_y, bounds[0], bounds[1])
        
        # Evaluate new point
        new_value = evaluate_function(new_x, new_y)
        
        # Calculate acceptance probability for simulated annealing
        if new_value < current_value:
            accept_prob = 1.0
        else:
            delta = new_value - current_value
            accept_prob = np.exp(-delta / temperature)
        
        # Accept or reject move
        if np.random.rand() < accept_prob:
            # Update momentum
            momentum_x = momentum_factor * momentum_x + (1 - momentum_factor) * (new_x - current_x)
            momentum_y = momentum_factor * momentum_y + (1 - momentum_factor) * (new_y - current_y)
            
            # Update current position
            current_x, current_y = new_x, new_y
            current_value = new_value
            
            # Update best solution if found
            if new_value < best_value:
                best_value = new_value
                best_x, best_y = new_x, new_y
        
        # Cool down temperature
        temperature *= cooling_rate
        
        # Add periodic large jumps every 100 iterations
        if i % 100 == 0:
            jump_x = np.random.uniform(bounds[0], bounds[1])
            jump_y = np.random.uniform(bounds[0], bounds[1])
            jump_value = evaluate_function(jump_x, jump_y)
            if jump_value < best_value:
                best_value = jump_value
                best_x, best_y = jump_x, jump_y

    # Local search refinement
    refinement_steps = 100
    step_size = 0.1
    for _ in range(refinement_steps):
        # Try points in a small neighborhood
        for dx in [-step_size, 0, step_size]:
            for dy in [-step_size, 0, step_size]:
                x = best_x + dx
                y = best_y + dy
                value = evaluate_function(x, y)
                if value < best_value:
                    best_value = value
                    best_x, best_y = x, y
        
        # Reduce step size for finer search
        step_size *= 0.5
    
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
