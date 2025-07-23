
#include <fmt/format.h>
#include <lorina/pla.hpp>
#include <mockturtle/mockturtle.hpp>

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

std::pair<double, double> synthesis(const std::string &aigPath, const std::string &genlibPath, const std::string &verilogPath) {
  /* read technology library */
  std::vector<mockturtle::gate> gates;
  if (lorina::read_genlib(genlibPath, mockturtle::genlib_reader(gates)) != lorina::return_code::success) {
    return std::make_pair(-1, -1);
  }
  mockturtle::tech_library_params tps;
  mockturtle::tech_library<5, mockturtle::classification_type::np_configurations> tech_lib(gates, tps);

  fmt::print("[i] processing {}\n", aigPath);
  /* read aig */
  mockturtle::aig_network aig;
  if (lorina::read_aiger(aigPath, mockturtle::aiger_reader(aig)) != lorina::return_code::success) {
    return std::make_pair(-1, -1);
  }
  // const uint32_t size_before = aig.num_gates();
  // const uint32_t depth_before = mockturtle::depth_view(aig).depth();
  auto start = std::chrono::high_resolution_clock::now();

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
  auto end = std::chrono::high_resolution_clock::now();
  auto resyn_time = std::chrono::duration<double>(end - start).count();
  std::cout << std::fixed << std::setprecision(2);
  std::cout << "resyn runtime: " << resyn_time << std::endl;

  /* library to map to technology */
  mockturtle::map_params ps2;
  ps2.cut_enumeration_ps.minimize_truth_table = true;
  ps2.cut_enumeration_ps.cut_limit = 24;
  mockturtle::map_stats st2;
  mockturtle::binding_view<mockturtle::klut_network> res2 = mockturtle::map(aig, tech_lib, ps2, &st2);
  // const auto cec2 = abc_cec_impl(res2, aigPath);
  fmt::print("[i] area: {}, gates: {}, depth: {}\n", st2.area, res2.num_gates(), mockturtle::depth_view(res2).depth());
  start = std::chrono::high_resolution_clock::now();
  std::cout << std::fixed << std::setprecision(2);
  std::cout << "mapping runtime: " << std::chrono::duration<double>(start - end).count() << std::endl;

  mockturtle::write_verilog_with_binding(res2, verilogPath);

  return std::make_pair(st2.area, resyn_time);
}

int main(int argc, char *argv[]) {
  if (argc < 4) {
    std::cerr << "Usage: " << argv[0] << " aigPath genlibPath verilogPath" << std::endl;
    return 1;
  }

  std::string aigPath = argv[1];
  std::string genlibPath = argv[2];
  std::string verilogPath = argv[3];

  synthesis(aigPath, genlibPath, verilogPath);
  return 0;
}