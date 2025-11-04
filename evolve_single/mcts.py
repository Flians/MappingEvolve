import math
from collections import defaultdict

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# Messages will propagate to root logger which handles console and file output


class MCTS:
    "Monte Carlo Tree Search."

    def __init__(self, exploration_weight=1, rollout_iterations=3):
        self.Q = defaultdict(int)  # total reward of each node
        self.N = defaultdict(int)  # total number of visits to each node
        self.children = dict()  # children of each node
        self.exploration_weight = exploration_weight
        self.rollout_iterations = rollout_iterations

    # this function is not useful in our case
    def choose(self, node):
        "Choose the best successor of a node."
        if node.is_terminal():
            raise RuntimeError(f"choose called on the terminal node {node}")

        if node not in self.children:
            return node.find_random_child()

        def score(n):
            if self.N[n] == 0:
                return float('-inf')  # avoid unseen moves
            return self.Q[n] / self.N[n]  # average reward

        return max(self.children[node], key=score)

    def _select(self, node):
        "Select an unexplored descendant of the given node."
        path = []
        while True:
            path.append(node)
            # node is either unexplored or terminal
            if node not in self.children or not self.children[node]:
                return path
            unexplored = self.children[node] - self.children.keys()
            if unexplored:
                n = unexplored.pop()
                path.append(n)
                return path
            node = self._uct_select(node)  # descend a layer deeper

    def _uct_select(self, node):
        "Select a child of node, balancing exploration and exploitation."

        # all children of node should already be expanded
        assert all(n in self.children for n in self.children[node])

        log_N_vertex = math.log(self.N[node])

        def uct(n):
            "Upper confidence bound for trees."
            return self.Q[n] / self.N[n] + self.exploration_weight * math.sqrt(log_N_vertex / self.N[n])

        return max(self.children[node], key=uct)

    def _expand(self, node):
        "Update the `children` dict with the children of `node`."
        if node in self.children:
            return  # already expanded
        self.children[node] = node.find_children()

    def _rollout(self, node):
        "Returns the max reward for a random simulation-path of `node`."
        rewards = []
        current_node = node
        for _ in range(self.rollout_iterations):
            current_node.ensure_initialized()
            rewards.append(current_node.reward())
            current_node = current_node.find_random_child()
        return max(rewards)  # return maximum reward along the entire path

    def _backpropagate(self, path, reward):
        "Send the reward back up the path to the ancestors of the leaf."
        for node in reversed(path):
            self.N[node] += 1
            self.Q[node] += reward

    def do_iteration(self, node):
        "Make the tree one layer better. (Train for one iteration.)"
        logger.info("===== Start MCTS Iteration =====")
        logger.info("Step 1: Perform Selection")
        path = self._select(node)
        leaf = path[-1]
        logger.info("Selected leaf node type: %s", leaf.__class__.__name__)

        logger.info("Step 2: Ensure Initialization of Selected Node")
        leaf.ensure_initialized()

        logger.info("Step 3: Perform Expansion of Selected Node")
        self._expand(leaf)

        # Only perform rollout/backpropagation if not at the root
        if leaf.parent is None:
            logger.info("Leaf node is root; skipping rollout and backpropagation.")
        else:
            logger.info("Step 4: Perform Rollout from Selected Node")
            reward = self._rollout(leaf)
            logger.info("Rollout completed with reward: %.2f", reward)

            logger.info("Step 5: Perform Backpropagation")
            self._backpropagate(path, reward)

        logger.info("===== MCTS Iteration Completed =====")
