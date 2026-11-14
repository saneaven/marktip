cmake_minimum_required(VERSION 3.15)

project(marktip LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT DEFINED SKBUILD_PROJECT_VERSION)
  set(SKBUILD_PROJECT_VERSION "0.7.3")
endif()

add_library(md4c STATIC
  third_party/md4c/src/md4c.c
  third_party/md4c/src/entity.c
)
target_include_directories(md4c PUBLIC third_party/md4c/src)
target_compile_definitions(md4c PRIVATE MD4C_USE_UTF8)
set_target_properties(md4c PROPERTIES POSITION_INDEPENDENT_CODE ON)

add_library(marktip_core STATIC
  src/ast.cpp
  src/content.cpp
  src/entities.cpp
  src/lift.cpp
  src/parser.cpp
  src/policy.cpp
  src/schema.cpp
  src/schema_builder.cpp
  src/serializer.cpp
  src/tags.cpp
  src/validate.cpp
  src/value.cpp
)
target_include_directories(marktip_core PUBLIC src)
target_link_libraries(marktip_core PRIVATE md4c)
set_target_properties(marktip_core PROPERTIES
  POSITION_INDEPENDENT_CODE ON
  CXX_VISIBILITY_PRESET hidden
)

if(MSVC)
  target_compile_options(marktip_core PRIVATE /O2)
else()
  target_compile_options(marktip_core PRIVATE -O3 -Wall -Wextra -Wpedantic)
endif()

option(MARKTIP_BUILD_PYTHON "Build the Python extension" ON)

if(MARKTIP_BUILD_PYTHON)
  set(PYBIND11_FINDPYTHON ON)
  find_package(pybind11 CONFIG REQUIRED)

  if(NOT DEFINED CMAKE_INTERPROCEDURAL_OPTIMIZATION)
    target_link_libraries(marktip_core PRIVATE pybind11::lto)
  endif()

  pybind11_add_module(_core
    bindings/python/module.cpp
    bindings/python/ast.cpp
    bindings/python/options.cpp
    bindings/python/markdown.cpp
  )
  target_link_libraries(_core PRIVATE marktip_core)
  target_compile_definitions(_core PRIVATE MARKTIP_VERSION="${SKBUILD_PROJECT_VERSION}")

  if(MSVC)
    target_compile_options(_core PRIVATE /O2)
  else()
    target_compile_options(_core PRIVATE -O3 -Wall -Wextra -Wpedantic)
  endif()

  install(TARGETS _core LIBRARY DESTINATION marktip)
endif()
