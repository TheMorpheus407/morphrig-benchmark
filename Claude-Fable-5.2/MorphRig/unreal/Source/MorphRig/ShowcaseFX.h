#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ShowcaseFX.generated.h"

class UStaticMesh;
class UStaticMeshComponent;
class UMaterialInterface;
class UMaterialInstanceDynamic;

/** Very small pooled effect system (basic shapes + one unlit material) used to make events visible in the showcase. */
UCLASS()
class MORPHRIG_API AShowcaseFX : public AActor
{
	GENERATED_BODY()
public:
	AShowcaseFX();
	virtual void Tick(float DeltaTime) override;

	static AShowcaseFX* Get(UWorld* World);

	enum EShape { Sphere, Cube, Cylinder, Plane };

	/** Spawns a shape that moves with Velocity and interpolates scale / opacity over Duration. Returns a handle (>0). */
	int32 Spawn(EShape Shape, const FVector& Location, const FRotator& Rotation, const FVector& ScaleStart, const FVector& ScaleEnd,
		const FLinearColor& Color, float Duration, const FVector& Velocity = FVector::ZeroVector, float Intensity = 6.f, float OpacityStart = 0.8f, float OpacityEnd = 0.f);
	/** Persistent element updated by the caller every tick (beams, charge orb). */
	void SetPersistent(FName Key, EShape Shape, const FTransform& Transform, const FLinearColor& Color, float Intensity = 8.f, float Opacity = 0.7f);
	void ClearPersistent(FName Key);
	/** A beam is a cylinder stretched between two points. */
	void SetBeam(FName Key, const FVector& From, const FVector& To, float Radius, const FLinearColor& Color, float Intensity = 10.f);
	void ClearAll();

private:
	struct FItem
	{
		TObjectPtr<UStaticMeshComponent> Comp;
		TObjectPtr<UMaterialInstanceDynamic> Mid;
		FVector Velocity = FVector::ZeroVector;
		FVector ScaleStart = FVector::OneVector, ScaleEnd = FVector::OneVector;
		float Age = 0.f, Duration = 0.f, OpacityStart = 1.f, OpacityEnd = 0.f;
		bool bActive = false;
		FName Key;
	};
	FItem& Acquire(EShape Shape);
	UStaticMesh* MeshFor(EShape Shape);

	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> Components;
	UPROPERTY(Transient)
	TArray<TObjectPtr<UMaterialInstanceDynamic>> Mids;
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> Material;
	UPROPERTY(Transient)
	TObjectPtr<UStaticMesh> Meshes[4];
	TArray<FItem> Items;
};
