// MorphRig - animation instance for the MORPHRIG cyberpunk operative.
//
// The animation graph is built at runtime in the proxy so the project does not
// depend on an editor authored asset.  Three sequence players form the graph:
//
//   base layer   - the body state (idle, locomotion, jump, death, performance)
//   action layer - one shot actions (melee, cast, reload, dash, hit, blink)
//   aim layer    - nine calibrated aim poses, blended onto the upper body
//
// The layers are blended by hand in FMorphRigAnimProxy::Evaluate.  The aim
// layer is masked to the spine_01 branch so the legs stay planted while the
// upper body tracks the aim direction.
//
// The game thread only writes the UPROPERTYs of UMorphRigAnimInstance; the
// worker thread picks them up in FMorphRigAnimProxy::UpdateAnimationNode and
// pushes them into the sequence players.  That keeps the node graph free of
// cross thread writes.
#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimNodeBase.h"
#include "Animation/AnimNode_SequencePlayer.h"
#include "Engine/DataTable.h"
#include "MorphRigAnimInstance.generated.h"

class UAnimSequence;

/** High level character state, mirrored by the animation controller. */
UENUM(BlueprintType)
enum class EMorphRigState : uint8
{
	Idle,
	Locomotion,
	Jump,
	Fall,
	Land,
	Dash,
	Blink,
	Attack,
	Cast,
	Channel,
	Charge,
	Hit,
	Disabled,
	Death,
	Respawn,
	Performance
};

/** One row of the clip inventory table. */
USTRUCT(BlueprintType)
struct FMorphRigClipEntry : public FTableRowBase
{
	GENERATED_BODY()

	/** Required clip id, for example walk_f. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	FString ClipName;

	/** Content path of the imported animation sequence. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	FString AssetPath;

	/** one_shot, loop or pose. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	FString Form;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	bool bLoop = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	float Duration = 0.0f;

	/** The Unreal animation layer this clip belongs to. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	FString Layer;

	/** in_place or root_motion. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	FString RootMotion;

	/** Comma separated event markers with their frame numbers. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	FString Markers;
};

/** Runtime animation graph for the Operative. */
USTRUCT()
struct FMorphRigAnimProxy : public FAnimInstanceProxy
{
	GENERATED_BODY()

	/** The body state layer. */
	FAnimNode_SequencePlayer_Standalone BasePlayer;

	/** The one shot action layer. */
	FAnimNode_SequencePlayer_Standalone ActionPlayer;

	/** The upper body aim layer. */
	FAnimNode_SequencePlayer_Standalone AimPlayer;

	/** Weight of the action layer, 0..1. */
	float ActionWeight = 0.0f;

	/** Weight of the aim layer, 0..1. */
	float AimWeight = 0.0f;

	/** Per compact pose bone weight that masks the aim layer to the upper body. */
	TArray<float> AimBoneWeights;

	/** The skeleton bone the aim layer branch starts at. */
	FName AimBranchBone = TEXT("spine_01");

	/** Asset time of the base layer at the previous evaluation. */
	float PreviousRootTime = -1.0f;

	/** True once the root motion of a clip has been measured. */
	bool bHavePreviousRoot = false;

	/** Set when the base layer switched to another clip. */
	bool bResetRootTime = false;

	/** The bone the root motion is measured on. */
	FName RootBoneName = TEXT("root");

	/** The sequence the root motion was measured on, for the log. */
	const UAnimSequence* LoggedRootSequence = nullptr;

	// FAnimInstanceProxy interface
	virtual void Initialize(UAnimInstance* InInstance) override;
	virtual bool Evaluate(FPoseContext& Output) override;
	virtual void UpdateAnimationNode(const FAnimationUpdateContext& InContext) override;
	virtual void CacheBones() override;
	// End of FAnimInstanceProxy interface

	/** Copy the anim instance state into the graph. Runs on the worker thread. */
	void SyncNodesFromInstance();

	/** Rebuild the per bone mask of the aim layer. */
	void BuildAimBoneWeights();

	/**
	 * Measure the root motion of the base layer.
	 *
	 * Unreal extracts the root motion of a sequence while the asset player is
	 * ticked.  That tick belongs to the animation blueprint graph, which this
	 * project builds by hand, so the delta between the root bone track of the
	 * previous and the current frame is measured here instead.  When the
	 * engine already delivered a motion the measurement is skipped so the two
	 * paths never add up twice.
	 */
	void ExtractRootMotion();
};

/** Animation instance of the Operative. */
UCLASS(BlueprintType)
class MORPHRIG_API UMorphRigAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
	virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override;
	virtual void NativeInitializeAnimation() override;
	virtual void NativeUpdateAnimation(float DeltaSeconds) override;

	/** Current high level state. */
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig")
	EMorphRigState State = EMorphRigState::Idle;

	/** Normalised movement direction in character space, +X right. */
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig")
	FVector2D MoveDirection = FVector2D::ZeroVector;

	/** Movement speed in cm/s. */
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig")
	float MoveSpeed = 0.0f;

	/** Aim yaw in degrees, + is to the character's right. */
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig")
	float AimYaw = 0.0f;

	/** Aim pitch in degrees, + is down. */
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig")
	float AimPitch = 0.0f;

	/** True while the upper body aim layer is active. */
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig")
	bool bAiming = false;

	/** 0 = LOD0, 1 = LOD1, 2 = LOD2. */
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig")
	int32 LODIndex = 0;

	/** Team accent colour. */
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig")
	FLinearColor TeamColor = FLinearColor(1.0f, 0.55f, 0.10f, 1.0f);

	/** Name of the clip that is currently driving the character. */
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	FString ActiveClip;

	/** Last event raised by the controller. */
	UPROPERTY(BlueprintReadOnly, Category = "MorphRig")
	FString LastEvent;

	/** Playback rate applied to the base layer. */
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig")
	float PlayRate = 1.0f;

	/** Base layer sequence, pushed into the graph on the worker thread. */
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig")
	TObjectPtr<UAnimSequenceBase> BaseSequence = nullptr;

	/** One shot action layer sequence. */
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig")
	TObjectPtr<UAnimSequenceBase> ActionSequence = nullptr;

	/** Upper body aim layer sequence. */
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig")
	TObjectPtr<UAnimSequenceBase> AimSequence = nullptr;

	/** Whether the base layer loops. */
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig")
	bool bBaseLoop = true;

	/** Weight of the action layer, 0..1. */
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig")
	float ActionWeight = 0.0f;

	/** Weight of the aim layer, 0..1. */
	UPROPERTY(BlueprintReadWrite, Category = "MorphRig")
	float AimWeight = 0.0f;

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void SetTeamColor(FLinearColor InColor);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void SetState(EMorphRigState InState);

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void SetActiveClip(const FString& InClip) { ActiveClip = InClip; }

	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void RaiseEvent(const FString& InEvent) { LastEvent = InEvent; }

	/** Push the base sequence to the runtime graph. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void ApplyBaseSequence(UAnimSequenceBase* Sequence, bool bLoop);

	/** Push the one shot action layer. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void ApplyActionSequence(UAnimSequenceBase* Sequence);

	/** Push the upper body aim layer. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void ApplyAimSequence(UAnimSequenceBase* Sequence);

	/** Fade the action layer in or out. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void ApplyActionWeight(float Weight);

	/** Fade the aim layer in or out. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	void ApplyAimWeight(float Weight);

	/** Current time of the base sequence in seconds. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	float GetBaseTime() const;

	/** Length of the base sequence in seconds. */
	UFUNCTION(BlueprintCallable, Category = "MorphRig")
	float GetBaseLength() const;
};
