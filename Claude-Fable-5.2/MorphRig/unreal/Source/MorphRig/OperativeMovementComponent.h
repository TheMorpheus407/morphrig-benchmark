#pragma once
#include "CoreMinimal.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "OperativeMovementComponent.generated.h"

/**
 * Character movement with an optional forced horizontal velocity. The state component feeds the per-tick root
 * track delta of dash clips (and host driven knock-back travel) through it, so the capsule is moved by the normal
 * walking code (floor following, step-up, sweeps) instead of the mesh sliding away from the capsule.
 */
UCLASS()
class MORPHRIG_API UOperativeMovementComponent : public UCharacterMovementComponent
{
	GENERATED_BODY()
public:
	void SetForcedVelocity(const FVector& InVelocity) { ForcedVelocity = InVelocity; bForcedVelocity = true; }
	void ClearForcedVelocity() { bForcedVelocity = false; }
	bool HasForcedVelocity() const { return bForcedVelocity; }

	virtual void CalcVelocity(float DeltaTime, float Friction, bool bFluid, float BrakingDeceleration) override;

private:
	bool bForcedVelocity = false;
	FVector ForcedVelocity = FVector::ZeroVector;
};
