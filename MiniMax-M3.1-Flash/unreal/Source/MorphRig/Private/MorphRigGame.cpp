// MorphRig - primary game module implementation.
//
// The showcase client is a plain monolithic game target, so the project needs
// the primary game module boilerplate.  It also provides the FMemory wrappers
// and the project name symbols that the monolithic link expects.
#include "Modules/ModuleManager.h"

IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, MorphRig, "MorphRig");
