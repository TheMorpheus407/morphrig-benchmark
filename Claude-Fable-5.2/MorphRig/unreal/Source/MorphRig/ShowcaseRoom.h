#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ShowcaseRoom.generated.h"

class UStaticMesh;
class UStaticMeshComponent;
class UMaterialInterface;
class UMaterialInstanceDynamic;

/** Demonstration room built from engine basic shapes at runtime: floor, ramp, steps, aim targets, prop station, viewer dais, lights. */
UCLASS()
class MORPHRIG_API AShowcaseRoom : public AActor
{
	GENERATED_BODY()
public:
	AShowcaseRoom();
	virtual void BeginPlay() override;

	static AShowcaseRoom* Get(UWorld* World);

	int32 NumTargets() const { return Targets.Num(); }
	FVector GetAimTargetLocation(int32 Index) const;
	void SetAimTargetLocation(int32 Index, const FVector& Location);
	void HighlightTarget(int32 Index);
	void SetLighting(float Key, float FillA, float FillB, float Sky);
	/** key light: shadow darkness (0..1) and source angle in degrees (penumbra width) */
	void SetKeyShadow(float Amount, float SourceAngleDeg);
	/** close-up key: direction and intensity scale of the key light; ResetKeyDirection restores the room default */
	void SetKeyDirection(const FRotator& Rot, float IntensityScale);
	void ResetKeyDirection();
	float KeyIntensity = 1.9f;
	float KeyScale = 1.f;
	FRotator KeyDefaultRot = FRotator(-52, 35, 0);
	int32 FindTargetAt(const FVector& RayOrigin, const FVector& RayDir, float Tolerance = 35.f) const;

	FVector SpawnPoint = FVector(0, 0, 92);
	FVector ViewerPoint = FVector(-700, 600, 96);
	FVector StationPoint = FVector(-560, -420, 92);
	FVector RampBottom = FVector(380, -550, 92);
	FVector RampTop = FVector(1150, -550, 254);
	FVector StepsTop = FVector(1150, -250, 254);
	FVector StepsBottom = FVector(560, -250, 92);
	static constexpr float RampAngleDeg = 20.f;
	static constexpr float StepHeight = 20.f;
	static constexpr float HalfExtent = 1500.f;

private:
	UStaticMeshComponent* AddShape(const TCHAR* Shape, const FVector& Location, const FRotator& Rotation, const FVector& Scale,
		const FLinearColor& Color, float Roughness = 0.75f, bool bCollision = true, const FLinearColor& Emissive = FLinearColor::Black, bool bGrid = false);

	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> Parts;
	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> Targets;
	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> TargetPoles;
	UPROPERTY(Transient)
	TArray<TObjectPtr<UMaterialInstanceDynamic>> TargetMids;
	UPROPERTY(Transient)
	TArray<TObjectPtr<UMaterialInstanceDynamic>> Mids;
	UPROPERTY(Transient)
	TArray<TObjectPtr<AActor>> Lights;
};
