add_executable(emap ${CMAKE_CURRENT_SOURCE_DIR}/main.cpp ${CMAKE_CURRENT_SOURCE_DIR}/evolve.cpp ${CMAKE_CURRENT_SOURCE_DIR}/emap.hpp)
target_link_libraries(emap PUBLIC mockturtle experiments fmt ${Python_LIBRARIES})
target_include_directories(emap PRIVATE ${Python_INCLUDE_DIRS})
add_dependencies(emap mockturtle)
