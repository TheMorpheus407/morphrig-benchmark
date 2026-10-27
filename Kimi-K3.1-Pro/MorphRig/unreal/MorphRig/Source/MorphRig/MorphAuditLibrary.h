#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Materials/MaterialInterface.h"
#include "MorphAuditLibrary.generated.h"

class USkeletalMesh;
class USkinnedMeshComponent;
class UAnimSequence;
class UAnimNotify;
class USkeleton;

UCLASS()
class MORPHRIG_API UMorphAuditLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable, Category="MorphRig|Audit")
    static int32 GetLODTriangleCount(USkeletalMesh* Mesh, int32 LODIndex);

    UFUNCTION(BlueprintCallable, Category="MorphRig|Audit")
    static int32 GetDeformationBoneCount(USkeletalMesh* Mesh);

    UFUNCTION(BlueprintCallable, Category="MorphRig|Audit")
    static int32 GetLODMorphTargetCount(USkeletalMesh* Mesh, int32 LODIndex);

    UFUNCTION(BlueprintCallable, Category="MorphRig|Audit", meta=(DevelopmentOnly))
    static bool SetMaterialSlots(USkeletalMesh* Mesh, const TArray<UMaterialInterface*>& Materials);

    UFUNCTION(BlueprintCallable, Category="MorphRig|Audit", meta=(DevelopmentOnly))
    static bool RebindSkeletonForCleanup(UObject* Asset, USkeleton* Skeleton);

    UFUNCTION(BlueprintCallable, Category="MorphRig|Audit")
    static bool SetNotifyName(UAnimSequence* Sequence, UAnimNotify* Notify, FName EventName);

    UFUNCTION(BlueprintCallable, Category="MorphRig|Audit")
    static FVector GetRootMotionDelta(UAnimSequence* Sequence, double StartTime, float DeltaSeconds);

    UFUNCTION(BlueprintCallable, Category="MorphRig|Audit")
    static FTransform GetMeshBoneRestTransform(USkeletalMesh* Mesh, FName BoneName);

    UFUNCTION(BlueprintCallable, Category="MorphRig|Audit")
    static FString DescribeBindPose(USkeletalMesh* Mesh);

    UFUNCTION(BlueprintCallable, Category="MorphRig|Audit")
    static bool GetLowestSkinnedBoneZ(USkinnedMeshComponent* Component, FName BoneName, float& OutMinZ);

    UFUNCTION(BlueprintCallable, Category="MorphRig|Audit")
    static FString DescribeSkinnedGeometry(USkinnedMeshComponent* Component);

    UFUNCTION(BlueprintCallable, Category="MorphRig|Audit", meta=(DevelopmentOnly))
    static bool AlignRootReferenceToAnimation(USkeletalMesh* Mesh, UAnimSequence* Sequence);

    UFUNCTION(BlueprintCallable, Category="MorphRig|Audit", meta=(DevelopmentOnly))
    static bool AlignAnimationRootToReference(USkeletalMesh* SourceMesh, USkeletalMesh* TargetMesh, const TArray<UAnimSequence*>& Sequences);

};
