cmake_minimum_required(VERSION 3.22)
project(JunonColosseumNative LANGUAGES CXX)
add_library(JunonColosseumNative SHARED src/main.cpp)
target_compile_features(JunonColosseumNative PRIVATE cxx_std_23)
set_property(TARGET JunonColosseumNative PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>DLL")
target_compile_definitions(JunonColosseumNative PRIVATE UE_GAME UE_BUILD_SHIPPING PLATFORM_WINDOWS PLATFORM_MICROSOFT OVERRIDE_PLATFORM_HEADER_NAME=Windows UBT_COMPILED_PLATFORM=Win64 UNICODE _UNICODE)
file(GLOB dependency_includes LIST_DIRECTORIES true "${UE4SS_SOURCE}/deps/first/*/include")
list(FILTER dependency_includes EXCLUDE REGEX "/Unreal/include$")
target_include_directories(JunonColosseumNative PRIVATE
    "${UE4SS_SOURCE}/UE4SS/include" ${dependency_includes}
    "${IMGUI_SOURCE}" "${IMGUI_TEXT_EDIT_SOURCE}"
    "${UE4SS_SOURCE}/../../header-deps/zydis-v4.1.0/include"
    "${UE4SS_SOURCE}/../../header-deps/zydis-v4.1.0/dependencies/zycore/include"
    "${UEPSEUDO_SOURCE}/include" "${UEPSEUDO_SOURCE}/generated_include"
    "${UEPSEUDO_SOURCE}/include/Unreal" "${UEPSEUDO_SOURCE}/include/Unreal/Core")
target_link_libraries(JunonColosseumNative PRIVATE "${UE4SS_IMPORT_LIB}")
set_target_properties(JunonColosseumNative PROPERTIES OUTPUT_NAME main)
