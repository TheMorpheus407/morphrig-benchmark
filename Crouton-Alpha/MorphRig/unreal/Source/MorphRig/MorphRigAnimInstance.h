// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "MorphRigAnimInstance.generated.h"

/**
 * Native animation controller for the Operative.
 * Covers: idle, 8-dir walk/run blend space (via directional sampling), sprint,
 * start/stop, turns/pivots, jump/fall/land, dash (root motion), blink, melee,
 * ranged (+layers), reload, casts, channel/charge, deploy, uplink,
 * additive hits, stun/knockup/knockdown/getup, sleep, death/respawn, greet/victory/defeat,
 * dialogue (+visemes), aim poses (upper-body layer).
 * Interruption: channel/charge/uplink abort to interrupt/cancel clips without snap-back.
 * Playback speed 0.5x-1.5x via CurrentSpeed clamp.
 */
UCLASS()
class UMorphRigAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:
	UPROPERTY(BlueprintReadWrite, Category="MorphRig")
	FString CurrentClip = TEXT("idle_combat");
	UPROPERTY(BlueprintReadWrite, Category="MorphRig")
	FString OverrideState;
	UPROPERTY(BlueprintReadWrite, Category="MorphRig")
	FVector2D MoveInput;
	UPROPERTY(BlueprintReadWrite, Category="MorphRig")
	float GroundSpeed = 0.0f;
	UPROPERTY(BlueprintReadWrite, Category="MorphRig")
	bool bIsInAir = false;
	UPROPERTY(BlueprintReadWrite, Category="MorphRig")
	float MoveAngleDeg = 0.0f;
	UPROPERTY(BlueprintReadWrite, Category="MorphRig")
	float AimYawDeg = 0.0f;
	UPROPERTY(BlueprintReadWrite, Category="MorphRig")
	float AimPitchDeg = 0.0f;
	UPROPERTY(BlueprintReadWrite, Category="MorphRig")
	float PlaybackRate = 1.0f;
	UPROPERTY(BlueprintReadWrite, Category="MorphRig")
	FString AdditiveClip;
	UPROPERTY(BlueprintReadWrite, Category="MorphRig")
	FString FacePreset = TEXT("neutral");
	UPROPERTY(BlueprintReadWrite, Category="MorphRig")
	FString Viseme = TEXT("M");

protected:
	virtual void NativeInitializeAnimation() override;
	virtual void NativeUpdateAnimation(float DeltaSeconds) override;

private:
	UPROPERTY()
	TMap<FString, TObjectPtr<UAnimSequence>> ClipLibrary;

	void EnsureLibrary();
	UAnimSequence* FindClip(const FString& Id);
};
