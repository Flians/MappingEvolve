
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

inline bool abc_compress2(const std::string &aigPath, mockturtle::aig_network &ntk_out) {
  // Generate a random output AIG filename in the system temp directory
#ifdef _WIN32
  const char *env_tmp = std::getenv("TEMP");
  const std::string tmp_dir = env_tmp ? env_tmp : ".";
#else
  const char *env_tmp = std::getenv("TMPDIR");
  const std::string tmp_dir = env_tmp ? env_tmp : "/tmp";
#endif
  std::random_device rd;
  std::mt19937_64 gen(rd());
  std::uniform_int_distribution<uint64_t> dis;
  const auto r = dis(gen);
  const std::string out_aig = fmt::format("{}/abc_compress2_{:016x}.aig", tmp_dir, r);

  std::string command = fmt::format("yosys-abc -q \"read_aiger {}; balance -l; rewrite -l; refactor -l; balance -l; rewrite -l; rewrite -z -l; balance -l; refactor -z -l; rewrite -z -l; balance -l; write_aiger {}\"", aigPath, out_aig);

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
#if defined(_WIN32)
  int exit_code = _pclose(pipe.release());
#else
  int status = pclose(pipe.release());
  int exit_code = -1;
  if (status != -1) {
    if (WIFEXITED(status)) {
      exit_code = WEXITSTATUS(status);
    } else {
      exit_code = -1; // abnormal termination
    }
  }
#endif

  // Check exit code and that output file was produced
  bool ok = (exit_code == 0);
  if (!ok) {
    fmt::print(stderr, "abc_compress2: command failed (exit {})\nCommand: {}\nOutput:{}\n",
               exit_code, command, result);
    return false;
  }

  return lorina::read_aiger(out_aig, mockturtle::aiger_reader(ntk_out)) == lorina::return_code::success;
}

void synthesis(const mockturtle::tech_library<5, mockturtle::classification_type::np_configurations> &tech_lib, const std::string &aigPath, const std::string &verilogPath, std::vector<double> &results) {
  results.resize(6, 0);

  /* read aig and do abc compress */
  // auto start = std::chrono::high_resolution_clock::now();
  mockturtle::aig_network aig;
  if (!abc_compress2(aigPath, aig)) {
    return;
  }
  // auto cec1 = abc_cec_impl(aig, aigPath);
  // auto end = std::chrono::high_resolution_clock::now();
  // std::cout << std::fixed << std::setprecision(2);
  // std::cout << "resyn runtime: " << std::chrono::duration<double>(end - start).count() << std::endl;

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
        {"c17", {0.530000, 6.000000, 42.660000, 2.000000, 0.000510}},
        {"c432", {10.250000, 101.000000, 296.930000, 12.000000, 0.015735}},
        {"c499", {41.000000, 360.000000, 258.300003, 12.000000, 0.027755}},
        {"c880", {20.580000, 194.000000, 266.590000, 12.000000, 0.022746}},
        {"c1355", {38.630000, 341.000000, 259.000002, 11.000000, 0.027446}},
        {"c1908", {25.730000, 228.000000, 305.950001, 13.000000, 0.027218}},
        {"c2670", {38.630000, 385.000000, 243.280003, 12.000000, 0.046496}},
        {"c3540", {66.170000, 613.000000, 425.870005, 20.000000, 0.057508}},
        {"c5315", {84.450000, 831.000000, 324.750002, 15.000000, 0.043446}},
        {"c6288", {195.570001, 1692.000000, 1037.720007, 46.000000, 0.053225}},
        {"c7552", {95.630000, 951.000000, 557.130003, 26.000000, 0.064268}}};
    for (auto const &benchmark : experiments::iscas_benchmarks()) {
      synthesis(tech_lib, experiments::benchmark_path(benchmark), "", results);
      // printf("%s: {area: %f, gates: %f, delay: %f, depth: %f, runtime: %f, nec: %f}\n", benchmark.c_str(), results[0], results[1], results[2], results[3], results[4], results[5]);
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