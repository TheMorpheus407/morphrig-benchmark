#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MorphAssetLibrary.generated.h"

class USkeletalMesh;
class UAnimSequence;
UCLASS()
class MORPHRIG_API UMorphAssetLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable,Category="MorphRig|Assets")
    static void AddAssetSocket(USkeletalMesh* Mesh,FName SocketName,FName BoneName,FVector Offset);
    UFUNCTION(BlueprintCallable,Category="MorphRig|Assets")
    static void AddAssetSocketAtComponentPosition(USkeletalMesh* Mesh,FName SocketName,FName BoneName,FVector Position);
    UFUNCTION(BlueprintPure,Category="MorphRig|Assets")
    static FString InspectSkeletalAsset(USkeletalMesh* Mesh);
    UFUNCTION(BlueprintPure,Category="MorphRig|Assets")
    static FString InspectAnimationAsset(UAnimSequence* Sequence);
    UFUNCTION(BlueprintPure,Category="MorphRig|Assets")
    static FString InspectBootSurface(USkeletalMesh* Mesh);
};
