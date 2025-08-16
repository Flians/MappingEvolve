// EVOLVE-BLOCK-START
#include "emap.hpp"

namespace mockturtle {
  namespace detail {
    template <class NtkDest, unsigned CutSize, typename CutData, class Ntk, unsigned NInputs>
    template <bool DO_AREA>
    void exact_map_impl<NtkDest, CutSize, CutData, Ntk, NInputs>::match_phase(node<Ntk> const &n, uint8_t phase) {
      float best_arrival = std::numeric_limits<float>::max();
      float best_area_flow = std::numeric_limits<float>::max();
      float best_area = std::numeric_limits<float>::max();
      uint32_t best_size = UINT32_MAX;
      uint8_t best_cut = 0u;
      uint8_t best_phase = 0u;
      uint8_t cut_index = 0u;
      auto index = ntk.node_to_index(n);

      auto &node_data = node_match[index];
      auto &cut_matches = matches[index];
      exact_supergate<NtkDest, NInputs> const *best_supergate = node_data.best_supergate[phase];

      /* recompute best match info */
      if (best_supergate != nullptr) {
        auto const &cut = cuts.cuts(index)[node_data.best_cut[phase]];
        auto &supergates = cut_matches[(cut)->data.match_index];

        /* permutate the children to the NPN-represenentative configuration */
        std::vector<uint32_t> children(NInputs, 0u);
        auto ctr = 0u;
        for (auto l : cut) {
          children[supergates.permutation[ctr++]] = l;
        }

        best_phase = node_data.phase[phase];
        best_arrival = 0.0f;
        best_area_flow = best_supergate->area + cut_leaves_flow(cut, n, phase);
        best_area = best_supergate->area;
        best_cut = node_data.best_cut[phase];
        best_size = cut.size();
        for (auto pin = 0u; pin < NInputs; pin++) {
          float arrival_pin = node_match[children[pin]].arrival[(best_phase >> pin) & 1] + best_supergate->tdelay[pin];
          best_arrival = std::max(best_arrival, arrival_pin);
        }
      }

      /* foreach cut */
      for (auto &cut : cuts.cuts(index)) {
        /* trivial cuts or not matched cuts */
        if ((*cut)->data.ignore) {
          ++cut_index;
          continue;
        }

        auto const &supergates = cut_matches[(*cut)->data.match_index];

        if (supergates.supergates[phase] == nullptr) {
          ++cut_index;
          continue;
        }

        /* permutate the children to the NPN-represenentative configuration */
        std::vector<uint32_t> children(NInputs, 0u);
        auto ctr = 0u;
        for (auto l : *cut) {
          children[supergates.permutation[ctr++]] = l;
        }

        /* match each gate and take the best one */
        for (auto const &gate : *supergates.supergates[phase]) {
          uint8_t complement = supergates.negation ^ gate.polarity;
          node_data.phase[phase] = complement;
          float area_local = gate.area + cut_leaves_flow(*cut, n, phase);
          float worst_arrival = 0.0f;
          for (auto pin = 0u; pin < NInputs; pin++) {
            float arrival_pin = node_match[children[pin]].arrival[(complement >> pin) & 1] + gate.tdelay[pin];
            worst_arrival = std::max(worst_arrival, arrival_pin);
          }

          if constexpr (DO_AREA) {
            if (worst_arrival > node_data.required[phase] + epsilon)
              continue;
          }

          if (compare_map<DO_AREA>(worst_arrival, best_arrival, area_local, best_area_flow, cut->size(), best_size)) {
            best_arrival = worst_arrival;
            best_area_flow = area_local;
            best_size = cut->size();
            best_cut = cut_index;
            best_area = gate.area;
            best_phase = complement;
            best_supergate = &gate;
          }
        }

        ++cut_index;
      }

      node_data.flows[phase] = best_area_flow;
      node_data.arrival[phase] = best_arrival;
      node_data.area[phase] = best_area;
      node_data.best_cut[phase] = best_cut;
      node_data.phase[phase] = best_phase;
      node_data.best_supergate[phase] = best_supergate;
    }

  } // namespace detail
} // namespace mockturtle
// EVOLVE-BLOCK-END

// This part remains fixed (not evolved)
// self-defined function api (ignoring pre-defined api)