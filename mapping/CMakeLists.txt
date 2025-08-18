add_executable(mapping ${CMAKE_CURRENT_SOURCE_DIR}/main.cpp ${CMAKE_CURRENT_SOURCE_DIR}/evolve.tpp ${CMAKE_CURRENT_SOURCE_DIR}/mapping.hpp)
target_link_libraries(mapping PUBLIC mockturtle experiments fmt ${Python_LIBRARIES})
target_include_directories(mapping PRIVATE ${Python_INCLUDE_DIRS})
add_dependencies(mapping mockturtle)
