// MorphRig - the interactive demonstration room.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MorphRigShowroom.generated.h"

class UStaticMeshComponent;
class UPointLightComponent;
class UMaterialInterface;

/**
 * Builds the showcase room in code: floor, ramp, steps, movable aim targets
 * and the prop contact station.  Everything is built from engine primitives
 * so the project has no external level dependency.
 */
UCLASS()
class MORPHRIG_API AMorphRigShowroom : public AActor
{
	GENERATED_BODY()

public:
	AMorphRigShowroom();

	virtual void BeginPlay() override;

	/** The movable aim targets, in world space. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	TArray<FVector> GetTargetLocations() const;

private:
	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> Targets;

	UPROPERTY()
	TObjectPtr<UPointLightComponent> KeyLight;

	UPROPERTY()
	TObjectPtr<UPointLightComponent> FillLight;

	UPROPERTY()
	TObjectPtr<UPointLightComponent> RimLight;

	UStaticMeshComponent* AddBox(const FVector& Location, const FVector& Extent,
								  const FVector& Rotation, UMaterialInterface* Material);
	UStaticMeshComponent* AddCylinder(const FVector& Location, float Radius,
									   float Height, UMaterialInterface* Material);
};
