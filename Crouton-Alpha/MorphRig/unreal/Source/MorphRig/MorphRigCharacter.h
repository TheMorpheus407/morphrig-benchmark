// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "Logging/LogMacros.h"
#include "MorphRigCharacter.generated.h"

class USpringArmComponent;
class UCameraComponent;
class UInputAction;
struct FInputActionValue;

/**
 * Operative showcase character: movement, camera modes, clip browser, facial panel,
 * team accent, LOD switching, instance toggle, deterministic demo sequence.
 */
UCLASS(abstract)
class AMorphRigCharacter : public ACharacter
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Components", meta = (AllowPrivateAccess = "true"))
	USpringArmComponent* CameraBoom;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Components", meta = (AllowPrivateAccess = "true"))
	UCameraComponent* FollowCamera;

protected:
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* JumpAction;
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* MoveAction;
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* LookAction;
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* MouseLookAction;

public:
	UPROPERTY(BlueprintReadWrite, Category="Showcase")
	FString CurrentClip = TEXT("idle_combat");
	UPROPERTY(BlueprintReadWrite, Category="Showcase")
	FString CurrentState = TEXT("Locomotion");
	UPROPERTY(BlueprintReadWrite, Category="Showcase")
	float PlaybackSpeed = 1.0f;
	UPROPERTY(BlueprintReadWrite, Category="Showcase")
	float AimYaw = 0.0f;
	UPROPERTY(BlueprintReadWrite, Category="Showcase")
	float AimPitch = 0.0f;
	UPROPERTY(BlueprintReadWrite, Category="Showcase")
	int32 TeamVariant = 0;
	UPROPERTY(BlueprintReadWrite, Category="Showcase")
	int32 LODIndex = 0;

public:
	AMorphRigCharacter();
	virtual void SetupPlayerInputComponent(class UInputComponent* PlayerInputComponent) override;
	virtual void BeginPlay() override;

protected:
	void Move(const FInputActionValue& Value);
	void Look(const FInputActionValue& Value);

public:
	UFUNCTION(BlueprintCallable, Category="Input")
	virtual void DoMove(float Right, float Forward);
	UFUNCTION(BlueprintCallable, Category="Input")
	virtual void DoLook(float Yaw, float Pitch);
	UFUNCTION(BlueprintCallable, Category="Input")
	virtual void DoJumpStart();
	UFUNCTION(BlueprintCallable, Category="Input")
	virtual void DoJumpEnd();

	UFUNCTION(BlueprintCallable, Category="Showcase")
	void PlayNamedClip(const FString& ClipId);
	UFUNCTION(BlueprintCallable, Category="Showcase")
	void ResetCharacter();
	UFUNCTION(BlueprintCallable, Category="Showcase")
	void SetAim(float YawDeg, float PitchDeg);
	UFUNCTION(BlueprintCallable, Category="Showcase")
	void SetPlaybackSpeed(float Speed);
	UFUNCTION(BlueprintCallable, Category="Showcase")
	void SetTeamVariant(int32 Variant);
	UFUNCTION(BlueprintCallable, Category="Showcase")
	void SetLOD(int32 Index);
	UFUNCTION(BlueprintCallable, Category="Showcase")
	void SetCameraMode(int32 Mode);
	UFUNCTION(BlueprintCallable, Category="Showcase")
	void SetFaceControl(float Value, int32 ControlIndex);
	UFUNCTION(BlueprintCallable, Category="Showcase")
	void RunDeterministicSequence();
	UFUNCTION(BlueprintCallable, Category="Showcase")
	void ToggleInstanceCount();
	UFUNCTION(BlueprintCallable, Category="Showcase")
	void InterruptAction();
	UFUNCTION(BlueprintCallable, Category="Showcase")
	FString GetStateTrace() const;

protected:
	TArray<FString> DemoSequence;
	int32 DemoIndex = 0;
	FTimerHandle DemoTimer;
	FTimerHandle TraceTimer;
	TArray<FString> TraceBuffer;
	bool bInterruptPending = false;
	UPROPERTY()
	TArray<TWeakObjectPtr<AActor>> Allies;

	void StepDemo();
	void LogTrace(const FString& Msg);

public:
	FORCEINLINE class USpringArmComponent* GetCameraBoom() const { return CameraBoom; }
	FORCEINLINE class UCameraComponent* GetFollowCamera() const { return FollowCamera; }
};
