// EVOLVE-BLOCK-START
#include "mapping.hpp"

namespace mockturtle::detail {
  template <class Ntk, unsigned CutSize, typename CutData, unsigned NInputs, classification_type Configuration>
  template <bool DO_AREA>
  void tech_map_impl<Ntk, CutSize, CutData, NInputs, Configuration>::match_phase(node<Ntk> const &n, uint8_t phase) {
    double best_arrival = std::numeric_limits<double>::max();
    double best_area_flow = std::numeric_limits<double>::max();
    float best_area = std::numeric_limits<float>::max();
    uint32_t best_size = UINT32_MAX;
    uint8_t best_cut = 0u;
    uint8_t best_phase = 0u;
    uint8_t cut_index = 0u;
    auto index = ntk.node_to_index(n);

    auto &node_data = node_match[index];
    auto &cut_matches = matches[index];
    supergate<NInputs> const *best_supergate = node_data.best_supergate[phase];

    /* recompute best match info */
    if (best_supergate != nullptr) {
      auto const &cut = cuts.cuts(index)[node_data.best_cut[phase]];

      best_phase = node_data.phase[phase];
      best_arrival = 0.0f;
      best_area_flow = best_supergate->area + cut_leaves_flow(cut, n, phase);
      best_area = best_supergate->area;
      best_cut = node_data.best_cut[phase];
      best_size = cut.size();

      auto ctr = 0u;
      for (auto l : cut) {
        double arrival_pin = node_match[l].arrival[(best_phase >> ctr) & 1] + best_supergate->tdelay[ctr];
        best_arrival = std::max(best_arrival, arrival_pin);
        ++ctr;
      }
    }

    /* foreach cut */
    for (auto &cut : cuts.cuts(index)) {
      /* trivial cuts or not matched cuts */
      if ((*cut)->data.ignore) {
        ++cut_index;
        continue;
      }

      auto const &supergates = cut_matches[(*cut)->data.match_index].supergates;
      auto const negation = cut_matches[(*cut)->data.match_index].negations[phase];

      if (supergates[phase] == nullptr) {
        ++cut_index;
        continue;
      }

      /* match each gate and take the best one */
      for (auto const &gate : *supergates[phase]) {
        uint8_t gate_polarity = gate.polarity ^ negation;
        node_data.phase[phase] = gate_polarity;
        double area_local = gate.area + cut_leaves_flow(*cut, n, phase);
        double worst_arrival = 0.0f;

        auto ctr = 0u;
        for (auto l : *cut) {
          double arrival_pin = node_match[l].arrival[(gate_polarity >> ctr) & 1] + gate.tdelay[ctr];
          worst_arrival = std::max(worst_arrival, arrival_pin);
          ++ctr;
        }

        if constexpr (DO_AREA) {
          if (worst_arrival > node_data.required[phase] + epsilon)
            continue;
        }

        // begin compare_map
        bool flag_compare_map = false;
        if constexpr (DO_AREA) {
          const double area_slack = 0.5 * static_cast<double>(lib_inv_area);
          if ((worst_arrival < best_arrival - epsilon) && (area_local <= best_area_flow + area_slack)) {
            flag_compare_map = true;
          } else {
            if (area_local < best_area_flow - epsilon) {
              flag_compare_map = true;
            } else if (area_local > best_area_flow + epsilon) {
              flag_compare_map = false;
            } else if (worst_arrival < best_arrival - epsilon) {
              flag_compare_map = true;
            } else if (worst_arrival > best_arrival + epsilon) {
              flag_compare_map = false;
            } else if (cut->size() < best_size) {
              flag_compare_map = true;
            }
          }
        } else {
          if (worst_arrival < best_arrival - epsilon) {
            flag_compare_map = true;
          } else if (worst_arrival > best_arrival + epsilon) {
            flag_compare_map = false;
          } else if (area_local < best_area_flow - epsilon) {
            flag_compare_map = true;
          } else if (area_local > best_area_flow + epsilon) {
            flag_compare_map = false;
          } else if (cut->size() < best_size) {
            flag_compare_map = true;
          }
        }
        if (flag_compare_map) {
          best_arrival = worst_arrival;
          best_area_flow = area_local;
          best_size = cut->size();
          best_cut = cut_index;
          best_area = gate.area;
          best_phase = gate_polarity;
          best_supergate = &gate;
        }
        // end compare_map
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

} // namespace mockturtle::detail
// EVOLVE-BLOCK-END

// This part remains fixed (not evolved)
// self-defined function api (ignoring pre-defined api)
namespace mockturtle::detail {
  template <class Ntk, unsigned CutSize, typename CutData, unsigned NInputs, classification_type Configuration>
  double tech_map_impl<Ntk, CutSize, CutData, NInputs, Configuration>::cut_leaves_flow(cut_t const &cut, node<Ntk> const &n, uint8_t phase) {
    double flow{0.0f};
    auto const &node_data = node_match[ntk.node_to_index(n)];

    uint8_t ctr = 0u;
    for (auto leaf : cut) {
      uint8_t leaf_phase = (node_data.phase[phase] >> ctr++) & 1;
      flow += node_match[leaf].flows[leaf_phase];
    }

    return flow;
  }
} // namespace mockturtle::detail