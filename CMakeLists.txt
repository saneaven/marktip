cmake_minimum_required(VERSION 3.15)

project(marktip LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT DEFINED SKBUILD_PROJECT_VERSION)
  set(SKBUILD_PROJECT_VERSION "0.8.1")
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
  src/form.cpp
  src/inherit.cpp
  src/lift.cpp
  src/parser.cpp
  src/policy.cpp
  src/schema.cpp
  src/schema_builder.cpp
  src/serializer.cpp
  src/spelling.cpp
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
option(MARKTIP_BUILD_WASM "Build the WebAssembly module" OFF)

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

if(MARKTIP_BUILD_WASM)
  add_library(yyjson STATIC third_party/yyjson/yyjson.c)
  target_include_directories(yyjson PUBLIC third_party/yyjson)
  target_compile_definitions(yyjson PUBLIC
    YYJSON_DISABLE_WRITER=1
    YYJSON_DISABLE_UTILS=1
    YYJSON_DISABLE_INCR_READER=1
    YYJSON_DISABLE_FILE=1
    YYJSON_DISABLE_NON_STANDARD=1
    YYJSON_DISABLE_FAST_FP_CONV=1
  )

  target_compile_options(marktip_core PRIVATE -fwasm-exceptions)

  add_executable(marktip_wasm
    bindings/wasm/module.cpp
    bindings/wasm/options.cpp
  )
  target_link_libraries(marktip_wasm PRIVATE marktip_core yyjson)
  target_compile_definitions(marktip_wasm PRIVATE MARKTIP_VERSION="${SKBUILD_PROJECT_VERSION}")
  target_compile_options(marktip_wasm PRIVATE -O3 -Wall -Wextra -Wpedantic -fwasm-exceptions)
  target_link_options(marktip_wasm PRIVATE
    -O3
    -fwasm-exceptions
    --no-entry
    -sMODULARIZE=1
    -sEXPORT_ES6=1
    -sENVIRONMENT=web,worker,node
    -sALLOW_MEMORY_GROWTH=1
    -sSTACK_SIZE=1048576
    "-sEXPORTED_FUNCTIONS=['_malloc','_free']"
    "-sEXPORTED_RUNTIME_METHODS=['HEAPU8']"
  )
  set_target_properties(marktip_wasm PROPERTIES OUTPUT_NAME marktip SUFFIX ".mjs")
endif()
