// EVOLVE-BLOCK-START
#include "mapping.hpp"

namespace mockturtle::detail {
  template <class Ntk, unsigned CutSize, typename CutData, unsigned NInputs, classification_type Configuration>
  template <bool SwitchActivity>
  void tech_map_impl<Ntk, CutSize, CutData, NInputs, Configuration>::match_phase_exact(node<Ntk> const &n, uint8_t phase) {
    double best_arrival = std::numeric_limits<double>::max();
    float best_exact_area = std::numeric_limits<float>::max();
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
      best_area = best_supergate->area;
      best_cut = node_data.best_cut[phase];
      best_size = cut.size();

      auto ctr = 0u;
      for (auto l : cut) {
        double arrival_pin = node_match[l].arrival[(best_phase >> ctr) & 1] + best_supergate->tdelay[ctr];
        best_arrival = std::max(best_arrival, arrival_pin);
        ++ctr;
      }

      /* if cut is implemented, remove it from the cover */
      if (!node_data.same_match && node_data.map_refs[phase]) {
        best_exact_area = cut_deref<SwitchActivity>(cuts.cuts(index)[best_cut], n, phase);
      } else {
        best_exact_area = cut_ref<SwitchActivity>(cuts.cuts(index)[best_cut], n, phase);
        cut_deref<SwitchActivity>(cuts.cuts(index)[best_cut], n, phase);
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
        node_data.area[phase] = gate.area;
        float area_exact = cut_ref<SwitchActivity>(*cut, n, phase);
        cut_deref<SwitchActivity>(*cut, n, phase);
        double worst_arrival = 0.0f;

        auto ctr = 0u;
        for (auto l : *cut) {
          double arrival_pin = node_match[l].arrival[(gate_polarity >> ctr) & 1] + gate.tdelay[ctr];
          worst_arrival = std::max(worst_arrival, arrival_pin);
          ++ctr;
        }

        if (worst_arrival > node_data.required[phase] + epsilon)
          continue;

        if (compare_map<true>(worst_arrival, best_arrival, area_exact, best_exact_area, cut->size(), best_size)) {
          best_arrival = worst_arrival;
          best_exact_area = area_exact;
          best_area = gate.area;
          best_size = cut->size();
          best_cut = cut_index;
          best_phase = gate_polarity;
          best_supergate = &gate;
        }
      }

      ++cut_index;
    }

    node_data.flows[phase] = best_exact_area;
    node_data.arrival[phase] = best_arrival;
    node_data.area[phase] = best_area;
    node_data.best_cut[phase] = best_cut;
    node_data.phase[phase] = best_phase;
    node_data.best_supergate[phase] = best_supergate;

    if (!node_data.same_match && node_data.map_refs[phase]) {
      best_exact_area = cut_ref<SwitchActivity>(cuts.cuts(index)[best_cut], n, phase);
    }
  }

} // namespace mockturtle::detail
// EVOLVE-BLOCK-END

// This part remains fixed (not evolved)
// self-defined function api (ignoring pre-defined api)
namespace mockturtle::detail {
#ifndef cut_ref_ENABLED
#define cut_ref_ENABLED
  template <class Ntk, unsigned CutSize, typename CutData, unsigned NInputs, classification_type Configuration>
  template <bool SwitchActivity>
  float tech_map_impl<Ntk, CutSize, CutData, NInputs, Configuration>::cut_ref(cut_t const &cut, node<Ntk> const &n, uint8_t phase) {
    auto const &node_data = node_match[ntk.node_to_index(n)];
    float count;

    if constexpr (SwitchActivity)
      count = switch_activity[ntk.node_to_index(n)];
    else
      count = node_data.area[phase];

    uint8_t ctr = 0;
    for (auto leaf : cut) {
      /* compute leaf phase using the current gate */
      uint8_t leaf_phase = (node_data.phase[phase] >> ctr++) & 1;

      if (ntk.is_constant(ntk.index_to_node(leaf))) {
        continue;
      } else if (ntk.is_ci(ntk.index_to_node(leaf))) {
        /* reference PIs, add inverter cost for negative phase */
        if (leaf_phase == 1u) {
          if (node_match[leaf].map_refs[1]++ == 0u) {
            if constexpr (SwitchActivity)
              count += switch_activity[leaf];
            else
              count += lib_inv_area;
          }
        } else {
          ++node_match[leaf].map_refs[0];
        }
        continue;
      }

      if (node_match[leaf].same_match) {
        /* Add inverter area if not present yet and leaf node is implemented in the opposite phase */
        if (node_match[leaf].map_refs[leaf_phase]++ == 0u && node_match[leaf].best_supergate[leaf_phase] == nullptr) {
          if constexpr (SwitchActivity)
            count += switch_activity[leaf];
          else
            count += lib_inv_area;
        }
        /* Recursive referencing if leaf was not referenced */
        if (node_match[leaf].map_refs[2]++ == 0u) {
          count += cut_ref<SwitchActivity>(cuts.cuts(leaf)[node_match[leaf].best_cut[leaf_phase]], ntk.index_to_node(leaf), leaf_phase);
        }
      } else {
        ++node_match[leaf].map_refs[2];
        if (node_match[leaf].map_refs[leaf_phase]++ == 0u) {
          count += cut_ref<SwitchActivity>(cuts.cuts(leaf)[node_match[leaf].best_cut[leaf_phase]], ntk.index_to_node(leaf), leaf_phase);
        }
      }
    }
    return count;
  }
#endif

#ifndef cut_deref_ENABLED
#define cut_deref_ENABLED
  template <class Ntk, unsigned CutSize, typename CutData, unsigned NInputs, classification_type Configuration>
  template <bool SwitchActivity>
  float tech_map_impl<Ntk, CutSize, CutData, NInputs, Configuration>::cut_deref(cut_t const &cut, node<Ntk> const &n, uint8_t phase) {
    auto const &node_data = node_match[ntk.node_to_index(n)];
    float count;

    if constexpr (SwitchActivity)
      count = switch_activity[ntk.node_to_index(n)];
    else
      count = node_data.area[phase];

    uint8_t ctr = 0;
    for (auto leaf : cut) {
      /* compute leaf phase using the current gate */
      uint8_t leaf_phase = (node_data.phase[phase] >> ctr++) & 1;

      if (ntk.is_constant(ntk.index_to_node(leaf))) {
        continue;
      } else if (ntk.is_ci(ntk.index_to_node(leaf))) {
        /* dereference PIs, add inverter cost for negative phase */
        if (leaf_phase == 1u) {
          if (--node_match[leaf].map_refs[1] == 0u) {
            if constexpr (SwitchActivity)
              count += switch_activity[leaf];
            else
              count += lib_inv_area;
          }
        } else {
          --node_match[leaf].map_refs[0];
        }
        continue;
      }

      if (node_match[leaf].same_match) {
        /* Add inverter area if it is used only by the current gate and leaf node is implemented in the opposite phase */
        if (--node_match[leaf].map_refs[leaf_phase] == 0u && node_match[leaf].best_supergate[leaf_phase] == nullptr) {
          if constexpr (SwitchActivity)
            count += switch_activity[leaf];
          else
            count += lib_inv_area;
        }
        /* Recursive dereferencing */
        if (--node_match[leaf].map_refs[2] == 0u) {
          count += cut_deref<SwitchActivity>(cuts.cuts(leaf)[node_match[leaf].best_cut[leaf_phase]], ntk.index_to_node(leaf), leaf_phase);
        }
      } else {
        --node_match[leaf].map_refs[2];
        if (--node_match[leaf].map_refs[leaf_phase] == 0u) {
          count += cut_deref<SwitchActivity>(cuts.cuts(leaf)[node_match[leaf].best_cut[leaf_phase]], ntk.index_to_node(leaf), leaf_phase);
        }
      }
    }
    return count;
  }
#endif

#ifndef compare_map_ENABLED
#define compare_map_ENABLED
  template <class Ntk, unsigned CutSize, typename CutData, unsigned NInputs, classification_type Configuration>
  template <bool DO_AREA>
  bool tech_map_impl<Ntk, CutSize, CutData, NInputs, Configuration>::compare_map(double arrival, double best_arrival, double area_flow, double best_area_flow, uint32_t size, uint32_t best_size) {
    if constexpr (DO_AREA) {
      if (area_flow < best_area_flow - epsilon) {
        return true;
      } else if (area_flow > best_area_flow + epsilon) {
        return false;
      } else if (arrival < best_arrival - epsilon) {
        return true;
      } else if (arrival > best_arrival + epsilon) {
        return false;
      }
    } else {
      if (arrival < best_arrival - epsilon) {
        return true;
      } else if (arrival > best_arrival + epsilon) {
        return false;
      } else if (area_flow < best_area_flow - epsilon) {
        return true;
      } else if (area_flow > best_area_flow + epsilon) {
        return false;
      }
    }
    if (size < best_size) {
      return true;
    }
    return false;
  }
#endif
} // namespace mockturtle::detail