cmake_minimum_required(VERSION 3.15)

project(marktip LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT DEFINED SKBUILD_PROJECT_VERSION)
  set(SKBUILD_PROJECT_VERSION "0.5.0")
endif()

set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)

add_library(md4c STATIC
  third_party/md4c/src/md4c.c
  third_party/md4c/src/entity.c
)
target_include_directories(md4c PUBLIC third_party/md4c/src)
target_compile_definitions(md4c PRIVATE MD4C_USE_UTF8)
set_target_properties(md4c PROPERTIES POSITION_INDEPENDENT_CODE ON)

pybind11_add_module(_core
  src/ast.cpp
  src/marktip.cpp
  src/parser.cpp
  src/serializer.cpp
)
target_link_libraries(_core PRIVATE md4c)
target_include_directories(_core PRIVATE third_party/md4c/src)
target_compile_definitions(_core PRIVATE MARKTIP_VERSION="${SKBUILD_PROJECT_VERSION}")

if(MSVC)
  target_compile_options(_core PRIVATE /O2)
else()
  target_compile_options(_core PRIVATE -O3 -Wall -Wextra -Wpedantic)
endif()

install(TARGETS _core LIBRARY DESTINATION marktip)
