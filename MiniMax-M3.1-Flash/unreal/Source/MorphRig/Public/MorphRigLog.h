// MorphRig - shared log category.
//
// The category is declared once here and defined exactly once in
// MorphRigCharacter.cpp so every translation unit can log without
// duplicate symbol errors.
#pragma once

#include "CoreMinimal.h"
#include "Logging/LogMacros.h"

DECLARE_LOG_CATEGORY_EXTERN(LogMorphRig, Log, All);
