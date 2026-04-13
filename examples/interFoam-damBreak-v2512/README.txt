interFoam laminar damBreak — OpenFOAM v2512 tutorial layout
Source: https://gitlab.com/openfoam/core/openfoam (tutorials/multiphase/interFoam/laminar/damBreak/damBreak)

ZIP root must unpack to system/, constant/, 0/ at the case top level.

Suggested commands:
  blockMesh && setFields && interFoam && foamToVTK

Fixes vs older snippets: system/fvSchemes includes ddtSchemes { default Euler; };
system/setFieldsDict is included for setFields after blockMesh.
