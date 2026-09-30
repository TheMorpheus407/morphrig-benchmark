#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MorphEditorTools.generated.h"

class USkeletalMesh;

/** Small helpers for the Python import script (properties Python cannot set directly). */
UCLASS()
class MORPHRIG_API UMorphEditorTools : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/** Adds (or updates) a socket on the mesh and its skeleton, attached to Bone with zero offset. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static bool AddSocket(USkeletalMesh* Mesh, FName Socket, FName Bone);

	/** Sets per-LOD screen sizes (index 0 = LOD0). */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static int32 SetLODScreenSizes(USkeletalMesh* Mesh, const TArray<float>& Sizes);
};
