// EVOLVE-BLOCK-START
#include "mapping.hpp"

namespace mockturtle::detail {
  template <class Ntk, unsigned CutSize, typename CutData, unsigned NInputs, classification_type Configuration>
  template <bool DO_AREA, bool ELA>
  void tech_map_impl<Ntk, CutSize, CutData, NInputs, Configuration>::match_drop_phase(node<Ntk> const &n, float required_margin_factor) {
    auto index = ntk.node_to_index(n);
    auto &node_data = node_match[index];

    /* compute arrival adding an inverter to the other match phase */
    double worst_arrival_npos = node_data.arrival[1] + lib_inv_delay;
    double worst_arrival_nneg = node_data.arrival[0] + lib_inv_delay;
    bool use_zero = false;
    bool use_one = false;

    /* only one phase is matched */
    if (node_data.best_supergate[0] == nullptr) {
      set_match_complemented_phase(index, 1, worst_arrival_npos);
      if constexpr (ELA) {
        if (node_data.map_refs[2])
          cut_ref<false>(cuts.cuts(index)[node_data.best_cut[1]], n, 1);
      }
      return;
    } else if (node_data.best_supergate[1] == nullptr) {
      set_match_complemented_phase(index, 0, worst_arrival_nneg);
      if constexpr (ELA) {
        if (node_data.map_refs[2])
          cut_ref<false>(cuts.cuts(index)[node_data.best_cut[0]], n, 0);
      }
      return;
    }

    /* try to use only one match to cover both phases */
    if constexpr (!DO_AREA) {
      /* if arrival improves matching the other phase and inserting an inverter */
      use_one = worst_arrival_npos < node_data.arrival[0] + epsilon;
      use_zero = worst_arrival_nneg < node_data.arrival[1] + epsilon;
    } else {
      /* check if both phases + inverter meet the required time */
      const double margin = required_margin_factor * lib_inv_delay;
      use_zero = worst_arrival_nneg < node_data.required[1] + epsilon - margin;
      use_one = worst_arrival_npos < node_data.required[0] + epsilon - margin;
    }

    /* condition on not used phases, evaluate a substitution during exact area recovery */
    if constexpr (ELA) {
      if (iteration != 0) {
        if (node_data.map_refs[0] == 0 || node_data.map_refs[1] == 0) {
          /* select the used match */
          auto phase = 0;
          auto nphase = 0;
          if (node_data.map_refs[0] == 0) {
            phase = 1;
            use_one = true;
            use_zero = false;
          } else {
            nphase = 1;
            use_one = false;
            use_zero = true;
          }
          /* select the not used match instead if it leads to area improvement and doesn't violate the required time */
          if (node_data.arrival[nphase] + lib_inv_delay < node_data.required[phase] + epsilon) {
            auto size_phase = cuts.cuts(index)[node_data.best_cut[phase]].size();
            auto size_nphase = cuts.cuts(index)[node_data.best_cut[nphase]].size();

            // begin compare_map
            double arrival = node_data.arrival[nphase] + lib_inv_delay;
            double best_arrival = node_data.arrival[phase];
            double area_flow = node_data.flows[nphase] + lib_inv_area;
            double best_area_flow = node_data.flows[phase];
            bool flag_compare_map = false;
            if constexpr (DO_AREA) {
              if (area_flow < best_area_flow - epsilon) {
                flag_compare_map = true;
              } else if (area_flow > best_area_flow + epsilon) {
                flag_compare_map = false;
              } else if (arrival < best_arrival - epsilon) {
                flag_compare_map = true;
              } else if (arrival > best_arrival + epsilon) {
                flag_compare_map = false;
              } else if (size_nphase < size_phase) {
                flag_compare_map = true;
              }
            } else {
              if (arrival < best_arrival - epsilon) {
                flag_compare_map = true;
              } else if (arrival > best_arrival + epsilon) {
                flag_compare_map = false;
              } else if (area_flow < best_area_flow - epsilon) {
                flag_compare_map = true;
              } else if (area_flow > best_area_flow + epsilon) {
                flag_compare_map = false;
              } else if (size_nphase < size_phase) {
                flag_compare_map = true;
              }
            }
            if (flag_compare_map) {
              /* invert the choice */
              use_zero = !use_zero;
              use_one = !use_one;
            }
            // end compare_map
          }
        }
      }
    }

    if (!use_zero && !use_one) {
      /* use both phases */
      node_data.flows[0] = node_data.flows[0] / node_data.est_refs[0];
      node_data.flows[1] = node_data.flows[1] / node_data.est_refs[1];
      node_data.flows[2] = node_data.flows[0] + node_data.flows[1];
      node_data.same_match = false;
      return;
    }

    /* use area flow as a tiebreaker with early exit optimization */
    if (use_zero && use_one) {
      const auto& cut_zero = cuts.cuts(index)[node_data.best_cut[0]];
      const auto& cut_one = cuts.cuts(index)[node_data.best_cut[1]];
      
      // Early exit if one cut is significantly smaller
      if (cut_zero.size() + 2 < cut_one.size()) {
        use_one = false;
        return;
      }
      if (cut_one.size() + 2 < cut_zero.size()) {
        use_zero = false;
        return;
      }

      // Compare area flows and arrival times
      const double area_diff = node_data.flows[0] - node_data.flows[1];
      const double arrival_diff = worst_arrival_nneg - worst_arrival_npos;
      
      if constexpr (DO_AREA) {
        if (area_diff < -epsilon || 
            (std::abs(area_diff) <= epsilon && arrival_diff < -epsilon) ||
            (std::abs(area_diff) <= epsilon && std::abs(arrival_diff) <= epsilon && cut_zero.size() < cut_one.size())) {
          use_one = false;
        } else {
          use_zero = false;
        }
      } else {
        if (arrival_diff < -epsilon ||
            (std::abs(arrival_diff) <= epsilon && area_diff < -epsilon) ||
            (std::abs(arrival_diff) <= epsilon && std::abs(area_diff) <= epsilon && cut_zero.size() < cut_one.size())) {
          use_one = false;
        } else {
          use_zero = false;
        }
      }
    }

    if (use_zero) {
      if constexpr (ELA) {
        /* set cut references */
        if (!node_data.same_match) {
          /* dereference the negative phase cut if in use */
          if (node_data.map_refs[1] > 0)
            cut_deref<false>(cuts.cuts(index)[node_data.best_cut[1]], n, 1);
          /* reference the positive cut if not in use before */
          if (node_data.map_refs[0] == 0 && node_data.map_refs[2])
            cut_ref<false>(cuts.cuts(index)[node_data.best_cut[0]], n, 0);
        } else if (node_data.map_refs[2])
          cut_ref<false>(cuts.cuts(index)[node_data.best_cut[0]], n, 0);
      }
      set_match_complemented_phase(index, 0, worst_arrival_nneg);
    } else {
      if constexpr (ELA) {
        /* set cut references */
        if (!node_data.same_match) {
          /* dereference the positive phase cut if in use */
          if (node_data.map_refs[0] > 0)
            cut_deref<false>(cuts.cuts(index)[node_data.best_cut[0]], n, 0);
          /* reference the negative cut if not in use before */
          if (node_data.map_refs[1] == 0 && node_data.map_refs[2])
            cut_ref<false>(cuts.cuts(index)[node_data.best_cut[1]], n, 1);
        } else if (node_data.map_refs[2])
          cut_ref<false>(cuts.cuts(index)[node_data.best_cut[1]], n, 1);
      }
      set_match_complemented_phase(index, 1, worst_arrival_npos);
    }
  }

} // namespace mockturtle::detail
// EVOLVE-BLOCK-END

// This part remains fixed (not evolved)
// self-defined function api (ignoring pre-defined api)
namespace mockturtle::detail {
  template <class Ntk, unsigned CutSize, typename CutData, unsigned NInputs, classification_type Configuration>
  void tech_map_impl<Ntk, CutSize, CutData, NInputs, Configuration>::set_match_complemented_phase(uint32_t index, uint8_t phase, double worst_arrival_n) {
    auto &node_data = node_match[index];
    auto phase_n = phase ^ 1;
    node_data.same_match = true;
    node_data.best_supergate[phase_n] = nullptr;
    node_data.best_cut[phase_n] = node_data.best_cut[phase];
    node_data.phase[phase_n] = node_data.phase[phase];
    node_data.arrival[phase_n] = worst_arrival_n;
    node_data.area[phase_n] = node_data.area[phase];
    node_data.flows[phase] = node_data.flows[phase] / node_data.est_refs[2];
    node_data.flows[phase_n] = node_data.flows[phase];
    node_data.flows[2] = node_data.flows[phase];
  }

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
} // namespace mockturtle::detail