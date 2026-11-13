#pragma once

#include "CoreMinimal.h"
#include "MorphRigTypes.generated.h"

UENUM(BlueprintType)
enum class EMorphRigPrimaryState : uint8
{
	Locomotion          UMETA(DisplayName = "Locomotion"),
	MobilityDash        UMETA(DisplayName = "Mobility: Dash (Root Motion)"),
	MobilityBlink       UMETA(DisplayName = "Mobility: Blink"),
	AbilityOneShot      UMETA(DisplayName = "Ability / Emote One-Shot"),
	ChannelStart        UMETA(DisplayName = "Channel: Start"),
	ChannelLoop         UMETA(DisplayName = "Channel: Sustained"),
	ChannelEnd          UMETA(DisplayName = "Channel: Complete"),
	ChannelInterrupt    UMETA(DisplayName = "Channel: Interrupted"),
	ChargeStart         UMETA(DisplayName = "Charge: Windup"),
	ChargeHold          UMETA(DisplayName = "Charge: Hold"),
	ChargeRelease       UMETA(DisplayName = "Charge: Release"),
	ChargeCancel        UMETA(DisplayName = "Charge: Cancel"),
	UplinkStart         UMETA(DisplayName = "Uplink: Start"),
	UplinkLoop          UMETA(DisplayName = "Uplink: Loop"),
	UplinkEnd           UMETA(DisplayName = "Uplink: Complete"),
	UplinkCancel        UMETA(DisplayName = "Uplink: Cancel"),
	DisableStunStart    UMETA(DisplayName = "Disable: Stun Start"),
	DisableStunLoop     UMETA(DisplayName = "Disable: Stun Loop"),
	DisableStunEnd      UMETA(DisplayName = "Disable: Stun Recovery"),
	DisableSleepStart   UMETA(DisplayName = "Disable: Sleep Start"),
	DisableSleepLoop    UMETA(DisplayName = "Disable: Sleep Loop"),
	DisableSleepEnd     UMETA(DisplayName = "Disable: Sleep Wake"),
	DisableKnockback    UMETA(DisplayName = "Disable: Knockback"),
	DisableKnockupStart UMETA(DisplayName = "Disable: Knockup Launch"),
	DisableKnockupAir   UMETA(DisplayName = "Disable: Knockup Airborne"),
	DisableKnockdown    UMETA(DisplayName = "Disable: Knockdown"),
	DisableProne        UMETA(DisplayName = "Disable: Prone Floor"),
	DisableGetup        UMETA(DisplayName = "Disable: Getup Recovery"),
	DeathDying          UMETA(DisplayName = "Terminal: Dying"),
	DeadHeld            UMETA(DisplayName = "Terminal: Dead (Held Pose)"),
	Respawning          UMETA(DisplayName = "Respawn Activation"),
	DirectClipInspect   UMETA(DisplayName = "Browser: Direct Clip Inspect")
};

UENUM(BlueprintType)
enum class EMorphRigUpperBodyMode : uint8
{
	None            UMETA(DisplayName = "None"),
	RangedFire      UMETA(DisplayName = "Ranged Single Fire"),
	RangedBurst     UMETA(DisplayName = "Ranged 3-Shot Burst"),
	Reload          UMETA(DisplayName = "Reload Cell"),
	CastDirectional UMETA(DisplayName = "Directional Cast")
};

UENUM(BlueprintType)
enum class EMorphRigCameraPreset : uint8
{
	OrbitClose      UMETA(DisplayName = "1: 3P Close Orbit"),
	FullBodyFront   UMETA(DisplayName = "2: Full-Body Front"),
	FullBodySide    UMETA(DisplayName = "3: Full-Body Side"),
	TopDownMOBA     UMETA(DisplayName = "4: 52-Deg Top-Down MOBA"),
	TopDown120Px    UMETA(DisplayName = "5: Top-Down ~120px Readability"),
	FacialCloseUp   UMETA(DisplayName = "6: Facial Close-Up"),
	RampStepsIK     UMETA(DisplayName = "7: Slope & Steps IK"),
	PropStation     UMETA(DisplayName = "8: Prop & Ten-Instance View")
};

USTRUCT(BlueprintType)
struct FMorphRigEventRecord
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	float WorldTimeSec = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	FName ClipId = NAME_None;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	FName MarkerName = NAME_None;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	FName LayerName = NAME_None;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	float ClipTimeSec = 0.0f;

	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	float PlayRate = 1.0f;
};

USTRUCT(BlueprintType)
struct FMorphRigFaceManualState
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	bool bEnableManualOverride = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float BlinkL = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float BlinkR = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float SquintL = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float SquintR = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float BrowUpL = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float BrowUpR = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float BrowDownL = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float BrowDownR = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float CheekRaiseL = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float CheekRaiseR = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float SmileL = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float SmileR = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float FrownL = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float FrownR = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float JawOpen = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float LipClose = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float MouthWide = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float MouthPucker = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float MouthFunnel = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float TongueUp = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float TongueOut = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	FName ActiveViseme = NAME_None;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float ActiveVisemeWeight = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	FName ActivePreset = NAME_None;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float ActivePresetWeight = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float EyeYawDeg = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Face")
	float EyePitchDeg = 0.0f;

	void Reset()
	{
		*this = FMorphRigFaceManualState();
	}
};
