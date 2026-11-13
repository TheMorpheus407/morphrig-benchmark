#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MorphRigEditorLibrary.generated.h"

class USkeletalMesh;
class UAnimSequence;
class UMaterialInterface;

/** Editor-time helpers used by tools/unreal_import.py for things the stock Python API cannot set. */
UCLASS()
class MORPHRIG_API UMorphRigEditorLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()
public:
	/** Creates or updates a mesh socket so that it sits at the given component-space rest transform. Returns the world error in cm. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static float AddOrUpdateSocket(USkeletalMesh* Mesh, FName SocketName, FName BoneName, FVector ComponentPosition, FVector ComponentForward, FVector ComponentUp);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static void RemoveAllSockets(USkeletalMesh* Mesh);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static TArray<FString> DescribeNotifies(UAnimSequence* Sequence);

	/** Number of triangles / vertices / skin influences of a rendered LOD (-1 when unavailable). */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static int32 GetLodTriangleCount(USkeletalMesh* Mesh, int32 LodIndex);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static int32 GetLodMaxBoneInfluences(USkeletalMesh* Mesh, int32 LodIndex);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static TArray<FName> GetRefBoneNames(USkeletalMesh* Mesh);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static TArray<FVector> GetRefBoneComponentPositions(USkeletalMesh* Mesh);

	/** Marks every listed curve name as a morph-target curve on the skeleton so sequences drive morphs directly. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static int32 MarkMorphCurves(USkeletalMesh* Mesh, const TArray<FName>& CurveNames);

	/** Largest vertex displacement (cm) of a morph target in a LOD, 0 when the LOD has no data, -1 when the morph does not exist. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static float GetMorphTargetMaxDelta(USkeletalMesh* Mesh, FName MorphName, int32 LodIndex);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static int32 GetMorphTargetVertexCount(USkeletalMesh* Mesh, FName MorphName, int32 LodIndex);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	static void SetLodScreenSizes(USkeletalMesh* Mesh, const TArray<float>& ScreenSizes);
};
