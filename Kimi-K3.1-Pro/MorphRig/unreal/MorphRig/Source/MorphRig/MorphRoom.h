#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MorphRoom.generated.h"

class UStaticMesh;
class UStaticMeshComponent;
class UMaterial;
class UTextureCube;
class UProceduralMeshComponent;

UCLASS()
class MORPHRIG_API AMorphRoom : public AActor
{
    GENERATED_BODY()

public:
    AMorphRoom();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    void SetTargetsMoving(bool bMoving) { bTargetsMoving = bMoving; }
    bool AreTargetsMoving() const { return bTargetsMoving; }

private:
    UStaticMeshComponent* AddBlock(FName Name, FVector Location, FVector Scale, FLinearColor Color, FRotator Rotation = FRotator::ZeroRotator, bool bCollision = true);
    void AddSign(FString Text, FVector Location, FRotator Rotation, FColor Color);

    UPROPERTY() USceneComponent* RoomRoot = nullptr;
    UPROPERTY() UStaticMesh* CubeAsset = nullptr;
    UPROPERTY() UStaticMesh* SphereAsset = nullptr;
    UPROPERTY() UMaterial* ShapeMaterial = nullptr;
    UPROPERTY() UTextureCube* AmbientSky = nullptr;
    UPROPERTY() UProceduralMeshComponent* RampCollision = nullptr;
    UPROPERTY() TArray<TObjectPtr<USceneComponent>> TargetRoots;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> TargetVisuals;
    FVector TargetOrigins[3];
    float Clock = 0.0f;
    bool bTargetsMoving = true;
};
