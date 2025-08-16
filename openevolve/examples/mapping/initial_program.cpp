// EVOLVE-BLOCK-START
template<bool DO_AREA>
void match_phase( node<Ntk> const& n, uint8_t phase )
  {
    auto index = ntk.node_to_index( n );
    auto& node_data = node_match[index];
    uint32_t cut_index = 0u;

    node_data.best_gate[phase] = nullptr;
    node_data.arrival[phase] = std::numeric_limits<float>::max();
    node_data.flows[phase] = std::numeric_limits<float>::max();
    node_data.area[phase] = std::numeric_limits<float>::max();
    uint32_t best_size = UINT32_MAX;

    best_gate_emap<NInputs>& gA = node_data.best_alternative[phase];
    gA.gate = nullptr;
    gA.arrival = std::numeric_limits<float>::max();
    gA.flow = std::numeric_limits<float>::max();
    uint32_t best_sizeA = UINT32_MAX;

    /* unmap multioutput */
    node_data.multioutput_match[phase] = false;

    /* foreach cut */
    for ( auto& cut : cuts[index] )
    {
      /* trivial cuts or not matched cuts */
      if ( ( *cut )->ignore )
      {
        ++cut_index;
        continue;
      }

      auto const& supergates = ( *cut )->supergates;
      auto const negation = ( *cut )->negations[phase];

      if ( supergates[phase] == nullptr )
      {
        ++cut_index;
        continue;
      }

      /* match each gate and take the best one */
      for ( auto const& gate : *supergates[phase] )
      {
        uint16_t gate_polarity = gate.polarity ^ negation;
        double worst_arrival = 0.0f;
        double worst_arrivalA = 0.0f;
        float area_local = gate.area;
        float area_localA = gate.area;

        auto ctr = 0u;
        for ( auto l : *cut )
        {
          uint8_t leaf_phase = ( gate_polarity >> ctr ) & 1;

          double arrival_pinA = node_match[l].best_alternative[leaf_phase].arrival + gate.tdelay[ctr];
          worst_arrivalA = std::max( worst_arrivalA, arrival_pinA );

          // if constexpr ( DO_AREA )
          // {
          //   if ( worst_arrivalA > node_data.required[phase] + epsilon || worst_arrivalA >= std::numeric_limits<float>::max() )
          //     break;
          // }

          double arrival_pin = node_match[l].arrival[leaf_phase] + gate.tdelay[ctr];
          worst_arrival = std::max( worst_arrival, arrival_pin );

          area_local += node_match[l].flows[leaf_phase];
          area_localA += node_match[l].best_alternative[leaf_phase].flow;
          ++ctr;
        }

        bool skip = false;
        if constexpr ( DO_AREA )
        {
          if ( ctr < cut->size() )
            continue;
          if ( worst_arrival > node_data.required[phase] + epsilon || worst_arrival >= std::numeric_limits<float>::max() )
            skip = true;
        }

        if ( !skip && compare_map<DO_AREA>( worst_arrival, node_data.arrival[phase], area_local, node_data.flows[phase], cut->size(), best_size ) )
        {
          node_data.best_gate[phase] = &gate;
          node_data.arrival[phase] = worst_arrival;
          node_data.flows[phase] = area_local;
          node_data.best_cut[phase] = cut_index;
          node_data.area[phase] = gate.area;
          node_data.phase[phase] = gate_polarity;
          best_size = cut->size();
        }

        /* compute the alternative */
        if ( compare_map<!DO_AREA>( worst_arrivalA, gA.arrival, area_localA, gA.flow, cut->size(), best_sizeA ) )
        {
          gA.gate = &gate;
          gA.arrival = worst_arrivalA;
          gA.area = gate.area;
          gA.flow = area_localA;
          gA.phase = gate_polarity;
          gA.cut = cut_index;
          best_sizeA = cut->size();
          gA.size = cut->size();
        }
      }

      ++cut_index;
    }
  }
// EVOLVE-BLOCK-END


// This part remains fixed (not evolved)
// self-defined function api (ignoring pre-defined api)