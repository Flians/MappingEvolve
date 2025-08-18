
#include "mapping.hpp"
#include <experiments.hpp>
#include <fmt/format.h>
#include <lorina/pla.hpp>
#include <mockturtle/algorithms/collapse_mapped.hpp>
#include <mockturtle/algorithms/lut_mapping.hpp>
#include <mockturtle/algorithms/node_resynthesis.hpp>
#include <mockturtle/algorithms/node_resynthesis/dsd.hpp>
#include <mockturtle/algorithms/node_resynthesis/exact.hpp>
#include <mockturtle/io/aiger_reader.hpp>
#include <mockturtle/io/write_bench.hpp>
#include <mockturtle/io/write_verilog.hpp>
#include <mockturtle/views/depth_view.hpp>
#include <mockturtle/views/mapping_view.hpp>

#include <chrono>
#include <iostream>
#include <string>
#include <vector>

#if defined(WIN32) || defined(_WIN32) || defined(__WIN32) && !defined(__CYGWIN__)
#define NULLL_PATH "NUL"
#define RM_CMD "del"
#define PATH_SEP "\\"
#else
#define NULLL_PATH "/dev/null"
#define RM_CMD "rm"
#define PATH_SEP "/"
#endif

template <class Ntk>
inline bool abc_cec_impl(Ntk const &ntk, std::string const &benchmark_fullpath) {
  mockturtle::write_bench(ntk, "/tmp/test.bench");
  std::string command = fmt::format("yosys-abc -q \"cec -n {} /tmp/test.bench\"", benchmark_fullpath);

  std::array<char, 128> buffer;
  std::string result;
#if WIN32
  std::unique_ptr<FILE, decltype(&_pclose)> pipe(_popen(command.c_str(), "r"), _pclose);
#else
  std::unique_ptr<FILE, decltype(&pclose)> pipe(popen(command.c_str(), "r"), pclose);
#endif
  if (!pipe) {
    throw std::runtime_error("popen() failed");
  }
  while (fgets(buffer.data(), buffer.size(), pipe.get()) != nullptr) {
    result += buffer.data();
  }

  /* search for one line which says "Networks are equivalent" and ignore all other debug output from ABC */
  std::stringstream ss(result);
  std::string line;
  while (std::getline(ss, line, '\n')) {
    if (line.size() >= 23u && line.substr(0u, 23u) == "Networks are equivalent") {
      return true;
    }
  }

  return false;
}

void synthesis(const mockturtle::tech_library<5, mockturtle::classification_type::np_configurations> &tech_lib, const std::string &aigPath, const std::string &verilogPath, std::vector<double> &results) {
  results.resize(6, 0);

  /* read aig */
  mockturtle::aig_network aig;
  if (lorina::read_aiger(aigPath, mockturtle::aiger_reader(aig)) != lorina::return_code::success) {
    return;
  }
  // const uint32_t size_before = aig.num_gates();
  // const uint32_t depth_before = mockturtle::depth_view(aig).depth();
  // auto start = std::chrono::high_resolution_clock::now();

  mockturtle::lut_mapping_params ps;
  ps.cut_enumeration_ps.cut_size = 4u;
  mockturtle::lut_mapping_stats st_lut;
  // collapse into k-LUT network
  mockturtle::mapping_view<mockturtle::aig_network, true> mapped_aig{aig};
  mockturtle::lut_mapping<decltype(mapped_aig), true>(mapped_aig, ps, &st_lut);
  mockturtle::klut_network klut = *mockturtle::collapse_mapped_network<mockturtle::klut_network>(mapped_aig);
  // node resynthesis
  mockturtle::exact_resynthesis_params ps_exact;
  ps_exact.cache = std::make_shared<mockturtle::exact_resynthesis_params::cache_map_t>();
  mockturtle::exact_aig_resynthesis<mockturtle::aig_network> exact_resyn(false, ps_exact);
  mockturtle::node_resynthesis_stats nrst;
  mockturtle::dsd_resynthesis<mockturtle::aig_network, decltype(exact_resyn)> resyn(exact_resyn);
  aig = mockturtle::node_resynthesis<mockturtle::aig_network>(klut, resyn, {}, &nrst);
  // auto cec1 = abc_cec_impl(aig, aigPath);
  // auto end = std::chrono::high_resolution_clock::now();
  // auto resyn_time = std::chrono::duration<double>(end - start).count();
  // std::cout << std::fixed << std::setprecision(2);
  // std::cout << "resyn runtime: " << resyn_time << std::endl;

  /* library to map to technology */
  mockturtle::map_params ps2;
  ps2.cut_enumeration_ps.minimize_truth_table = true;
  ps2.cut_enumeration_ps.cut_limit = 24;
  mockturtle::map_stats st2;
  mockturtle::binding_view<mockturtle::klut_network> res2 = mockturtle::map(aig, tech_lib, ps2, &st2);
  const auto cec2 = abc_cec_impl(res2, aigPath);

  results[0] = st2.area;
  results[1] = res2.num_gates();
  results[2] = st2.delay;
  results[3] = mockturtle::depth_view(res2).depth();
  results[4] = std::chrono::duration<double>(st2.time_total).count();
  results[5] = cec2 ? 0.0 : 1.0;
  /*
  fmt::print("[i] area: {}, gates: {}, depth: {}\n", st2.area, res2.num_gates(), mockturtle::depth_view(res2).depth());
  start = std::chrono::high_resolution_clock::now();
  std::cout << std::fixed << std::setprecision(2);
  std::cout << "mapping runtime: " << std::chrono::duration<double>(start - end).count() << std::endl;
  */
  if (!verilogPath.empty()) mockturtle::write_verilog_with_binding(res2, verilogPath);
}

int main(int argc, char *argv[]) {
  if (argc < 2) {
    std::cerr << "Usage: " << argv[0] << " genlibPath <aigPath> <verilogPath>" << std::endl;
    return 1;
  }

  std::string genlibPath = argv[1];

  /* read technology library */
  std::vector<mockturtle::gate> gates;
  if (lorina::read_genlib(genlibPath, mockturtle::genlib_reader(gates)) != lorina::return_code::success) {
    return 1;
  }
  mockturtle::tech_library_params tps;
  mockturtle::tech_library<5, mockturtle::classification_type::np_configurations> tech_lib(gates, tps);

  std::vector<double> results(6, 0);
  if (argc > 2) {
    std::string aigPath = argv[2];
    std::string verilogPath = argv[3];
    synthesis(tech_lib, aigPath, verilogPath, results);
  } else {
    std::vector<double> total(6, 0);
    const std::map<std::string, std::vector<double>> baselines = {
        {"c17", {0.530000, 6.000000, 42.660000, 2.000000, 0.000267}},
        {"c432", {18.100000, 175.000000, 330.510002, 15.000000, 0.022387}},
        {"c499", {40.910000, 364.000000, 295.020002, 12.000000, 0.013557}},
        {"c880", {24.310000, 220.000000, 316.219999, 13.000000, 0.013352}},
        {"c1355", {41.240000, 361.000000, 294.730001, 12.000000, 0.013666}},
        {"c1908", {30.390000, 280.000000, 433.749994, 18.000000, 0.011652}},
        {"c2670", {48.140000, 470.000000, 255.770004, 12.000000, 0.027633}},
        {"c3540", {66.440000, 604.000000, 425.960001, 19.000000, 0.054315}},
        {"c5315", {111.520001, 1102.000000, 406.700001, 19.000000, 0.037087}},
        {"c6288", {249.930001, 2403.000000, 969.780003, 47.000000, 0.058662}},
        {"c7552", {113.800000, 1144.000000, 383.960003, 18.000000, 0.061442}}};
    for (auto const &benchmark : experiments::iscas_benchmarks()) {
      // printf("[i] processing %s\n", benchmark.c_str());
      synthesis(tech_lib, experiments::benchmark_path(benchmark), "", results);
      // printf("{area: %f, gates: %f, delay: %f, depth: %f, runtime: %f, nec: %f}\n", results[0], results[1], results[2], results[3], results[4], results[5]);
      const auto &baseline = baselines.at(benchmark);
      for (size_t i = 0; i < results.size() - 1; ++i) {
        total[i] += (baseline[i] - results[i]) / baseline[i];
      }
      total[5] += results.back();
    }
    total[5] /= experiments::iscas_benchmarks().size();
    results = total;
  }
  printf("{\"area\": %f, \"gates\": %f, \"delay\": %f, \"depth\": %f, \"runtime\": %f, \"nec\": %f}\n", results[0], results[1], results[2], results[3], results[4], results[5]);

  return 0;
}