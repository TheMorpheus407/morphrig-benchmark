// MorphRig - animation instance implementation.
#include "MorphRigAnimInstance.h"
#include "MorphRigLog.h"

#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimationAsset.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimSequenceBase.h"
#include "Animation/AnimTypes.h"
#include "BonePose.h"
#include "MorphRigPerfLogger.h"
#include "ReferenceSkeleton.h"

namespace MorphRigAnimPrivate
{
	/** Blend two local space transforms. Alpha 0 keeps A, alpha 1 takes B. */
	static FTransform BlendTransforms(const FTransform& A, const FTransform& B, float Alpha)
	{
		FTransform Result;
		Result.SetTranslation(FMath::Lerp(A.GetTranslation(), B.GetTranslation(), Alpha));
		Result.SetRotation(FQuat::Slerp(A.GetRotation(), B.GetRotation(), Alpha));
		Result.SetScale3D(FMath::Lerp(A.GetScale3D(), B.GetScale3D(), Alpha));
		return Result;
	}

	/**
	 * Blend a layer pose into the output pose.
	 *
	 * @param Out       the pose that is being built, the base pose.
	 * @param Layer     the pose of the layer that is blended on top.
	 * @param Weight    the layer weight, 0..1.
	 * @param Mask      optional per bone weight, overrides Weight when supplied.
	 */
	static void BlendLayer(FPoseContext& Out, const FPoseContext& Layer, float Weight,
						   const TArray<float>* Mask)
	{
		for (FCompactPoseBoneIndex BoneIndex : Out.Pose.ForEachBoneIndex())
		{
			float BlendWeight = Weight;
			if (Mask)
			{
				BlendWeight = Mask->IsValidIndex(BoneIndex.GetInt())
					? (*Mask)[BoneIndex.GetInt()]
					: 0.0f;
			}
			if (BlendWeight <= 0.0f)
			{
				continue;
			}
			if (BlendWeight >= 1.0f)
			{
				Out.Pose[BoneIndex] = Layer.Pose[BoneIndex];
				continue;
			}
			Out.Pose[BoneIndex] = BlendTransforms(Out.Pose[BoneIndex],
												 Layer.Pose[BoneIndex], BlendWeight);
		}
		Out.Pose.NormalizeRotations();

		// The face morph curves live in the base layer, a weighted blend keeps
		// them intact because the upper layers carry no face animation.
		FBlendedCurve Blended;
		Blended.Lerp(Out.Curve, Layer.Curve, Weight);
		Out.Curve = Blended;
	}
}

// ---------------------------------------------------------------------------
// proxy
// ---------------------------------------------------------------------------

void FMorphRigAnimProxy::Initialize(UAnimInstance* InInstance)
{
	FAnimInstanceProxy::Initialize(InInstance);

	ActionWeight = 0.0f;
	AimWeight = 0.0f;
	AimBoneWeights.Reset();

	FAnimationInitializeContext InitContext(this);
	BasePlayer.Initialize_AnyThread(InitContext);
	ActionPlayer.Initialize_AnyThread(InitContext);
	AimPlayer.Initialize_AnyThread(InitContext);
}

void FMorphRigAnimProxy::CacheBones()
{
	FAnimInstanceProxy::CacheBones();

	FAnimationCacheBonesContext Context(this);
	BasePlayer.CacheBones_AnyThread(Context);
	ActionPlayer.CacheBones_AnyThread(Context);
	AimPlayer.CacheBones_AnyThread(Context);
}

void FMorphRigAnimProxy::UpdateAnimationNode(const FAnimationUpdateContext& InContext)
{
	SyncNodesFromInstance();

	BasePlayer.Update_AnyThread(InContext);
	ActionPlayer.Update_AnyThread(InContext);
	AimPlayer.Update_AnyThread(InContext);
}

void FMorphRigAnimProxy::SyncNodesFromInstance()
{
	const UMorphRigAnimInstance* Instance = Cast<UMorphRigAnimInstance>(GetAnimInstanceObject());
	if (!Instance)
	{
		return;
	}

	// ---- base layer ----
	if (BasePlayer.GetSequence() != Instance->BaseSequence)
	{
		BasePlayer.SetSequence(Instance->BaseSequence);
		BasePlayer.SetLoopAnimation(Instance->bBaseLoop);
		BasePlayer.SetStartPosition(0.0f);
		// Re-initialising restarts the clip at its first frame.
		FAnimationInitializeContext InitContext(this);
		BasePlayer.Initialize_AnyThread(InitContext);
		// The root motion of the new clip is measured from its first frame,
		// the previous clip never carried any.
		bResetRootTime = true;
	}
	BasePlayer.SetPlayRate(Instance->PlayRate);

	// ---- action layer ----
	if (ActionPlayer.GetSequence() != Instance->ActionSequence)
	{
		ActionPlayer.SetSequence(Instance->ActionSequence);
		ActionPlayer.SetLoopAnimation(false);
		ActionPlayer.SetStartPosition(0.0f);
		FAnimationInitializeContext InitContext(this);
		ActionPlayer.Initialize_AnyThread(InitContext);
	}

	// ---- aim layer ----
	if (AimPlayer.GetSequence() != Instance->AimSequence)
	{
		AimPlayer.SetSequence(Instance->AimSequence);
		AimPlayer.SetLoopAnimation(true);
		AimPlayer.SetStartPosition(0.0f);
		FAnimationInitializeContext InitContext(this);
		AimPlayer.Initialize_AnyThread(InitContext);
	}

	ActionWeight = FMath::Clamp(Instance->ActionWeight, 0.0f, 1.0f);
	AimWeight = FMath::Clamp(Instance->AimWeight, 0.0f, 1.0f);
}

void FMorphRigAnimProxy::BuildAimBoneWeights()
{
	const FBoneContainer& Bones = GetRequiredBones();
	const int32 NumBones = Bones.GetCompactPoseNumBones();
	if (NumBones <= 0)
	{
		return;
	}

	if (AimBoneWeights.Num() != NumBones)
	{
		AimBoneWeights.SetNumZeroed(NumBones);
	}
	else
	{
		for (float& Weight : AimBoneWeights)
		{
			Weight = 0.0f;
		}
	}

	if (AimWeight <= 0.0f)
	{
		return;
	}

	const FReferenceSkeleton& RefSkeleton = Bones.GetReferenceSkeleton();
	const int32 BranchBone = RefSkeleton.FindBoneIndex(AimBranchBone);
	if (BranchBone == INDEX_NONE)
	{
		return;
	}

	const TArray<FBoneIndexType>& BoneIndices = Bones.GetBoneIndicesArray();
	for (int32 CompactIndex = 0; CompactIndex < NumBones; ++CompactIndex)
	{
		if (!BoneIndices.IsValidIndex(CompactIndex))
		{
			continue;
		}
		const int32 SkeletonIndex = static_cast<int32>(BoneIndices[CompactIndex]);

		// walk up the skeleton hierarchy and look for the branch bone
		int32 Current = SkeletonIndex;
		int32 Guard = 0;
		while (Current != INDEX_NONE && Guard++ < 512)
		{
			if (Current == BranchBone)
			{
				AimBoneWeights[CompactIndex] = AimWeight;
				break;
			}
			Current = RefSkeleton.GetParentIndex(Current);
		}
	}
}

void FMorphRigAnimProxy::ExtractRootMotion()
{
	UAnimSequence* Sequence = Cast<UAnimSequence>(BasePlayer.GetSequence());
	if (!Sequence || !Sequence->HasRootMotion())
	{
		bHavePreviousRoot = false;
		return;
	}

	// Unreal extracts the root motion of a sequence from the translation of
	// the first bone of the skeleton.  The Operative has an armature bone
	// above the root bone, so the root bone is looked up by name.
	const FBoneContainer& Bones = GetRequiredBones();
	const FReferenceSkeleton& RefSkeleton = Bones.GetReferenceSkeleton();
	const int32 RootSkeletonIndex = RefSkeleton.FindBoneIndex(RootBoneName);
	if (RootSkeletonIndex == INDEX_NONE)
	{
		bHavePreviousRoot = false;
		return;
	}
	const TArray<FBoneIndexType>& BoneIndices = Bones.GetBoneIndicesArray();
	int32 RootCompact = INDEX_NONE;
	for (int32 Index = 0; Index < BoneIndices.Num(); ++Index)
	{
		if (BoneIndices[Index] == RootSkeletonIndex)
		{
			RootCompact = Index;
			break;
		}
	}
	if (RootCompact == INDEX_NONE)
	{
		bHavePreviousRoot = false;
		return;
	}
	const FCompactPoseBoneIndex RootCompactIndex(RootCompact);
	const FSkeletonPoseBoneIndex RootBoneIndex =
		Bones.GetSkeletonPoseIndexFromCompactPoseIndex(RootCompactIndex);

	// The root bone hangs below the armature bone, the parent frame is the
	// frame the root motion is expressed in.  The scale of the reference pose
	// is dropped: the exporter writes the unit scale of the file into it.
	const int32 ParentIndex = RefSkeleton.GetParentIndex(RootSkeletonIndex);
	const FTransform ParentRef = (ParentIndex != INDEX_NONE)
		? RefSkeleton.GetRefBonePose()[ParentIndex]
		: FTransform::Identity;
	const FTransform ParentFrame(ParentRef.GetRotation(), ParentRef.GetTranslation(),
								  FVector::OneVector);

	const float CurrentTime = BasePlayer.GetCurrentAssetTime();
	float PreviousTime = PreviousRootTime;
	if (bResetRootTime)
	{
		// The clip starts at zero, so the first frame of the new clip is
		// measured against the first frame of the clip and not against the
		// frame before it.
		bResetRootTime = false;
		PreviousTime = 0.0f;
		bHavePreviousRoot = true;
	}
	else if (!bHavePreviousRoot)
	{
		// The first frame of a clip has no delta to report.
		PreviousRootTime = CurrentTime;
		bHavePreviousRoot = true;
		return;
	}

	// The engine path wins when it delivered something: the two paths must
	// never add up twice.
	const FRootMotionMovementParams& EngineMotion = GetExtractedRootMotion();
	const bool bEngineDelivered = EngineMotion.bHasRootMotion &&
		!EngineMotion.GetRootMotionTransform().GetTranslation().IsNearlyZero(0.1f);

	if (!bEngineDelivered)
	{
		FAnimExtractContext Context(static_cast<double>(PreviousTime), true,
									 FDeltaTimeRecord(0.0f), false);
		FTransform Start;
		Sequence->GetBoneTransform(Start, RootBoneIndex, Context, false);
		Context.CurrentTime = static_cast<double>(CurrentTime);
		FTransform End;
		Sequence->GetBoneTransform(End, RootBoneIndex, Context, false);

		// The displacement of the root bone in the frame of its parent, which
		// is the frame the movement component expects the root motion in.
		// Unreal composes transforms as "A * B applies A and then B", so the
		// parent frame is the second factor.  The scale of the bone track is
		// dropped: the exporter writes the unit scale of the file into it,
		// the decompressor removes it again.
		const FTransform StartClean(Start.GetRotation(), Start.GetTranslation(),
									 FVector::OneVector);
		const FTransform EndClean(End.GetRotation(), End.GetTranslation(),
								  FVector::OneVector);
		const FTransform ComponentStart = StartClean * ParentFrame;
		const FTransform ComponentEnd = EndClean * ParentFrame;
		const FTransform Delta(
			ComponentStart.GetRotation().Inverse() * ComponentEnd.GetRotation(),
			ComponentEnd.GetTranslation() - ComponentStart.GetTranslation(),
			FVector::OneVector);
		GetExtractedRootMotion().Accumulate(Delta);

		if (LoggedRootSequence != Sequence)
		{
			LoggedRootSequence = Sequence;
			UE_LOG(LogMorphRig, Log, TEXT("root motion %s: %s cm"),
				   *Sequence->GetName(),
				   *Delta.GetTranslation().ToCompactString());
		}
	}

	PreviousRootTime = CurrentTime;
}

bool FMorphRigAnimProxy::Evaluate(FPoseContext& Output)
{
	// The base layer always provides the starting pose.
	{
		FPoseContext BaseContext(this);
		BasePlayer.Evaluate_AnyThread(BaseContext);
		Output = BaseContext;
	}

	// The dash clips carry the root motion that drives the capsule.
	ExtractRootMotion();

	// The action layer replaces the whole body.
	if (ActionWeight > KINDA_SMALL_NUMBER && ActionPlayer.GetSequence() != nullptr)
	{
		FPoseContext ActionContext(this);
		ActionPlayer.Evaluate_AnyThread(ActionContext);
		MorphRigAnimPrivate::BlendLayer(Output, ActionContext, ActionWeight, nullptr);
	}

	// The aim layer only touches the upper body so the legs stay planted.
	if (AimWeight > KINDA_SMALL_NUMBER && AimPlayer.GetSequence() != nullptr)
	{
		FPoseContext AimContext(this);
		AimPlayer.Evaluate_AnyThread(AimContext);
		BuildAimBoneWeights();
		MorphRigAnimPrivate::BlendLayer(Output, AimContext, AimWeight, &AimBoneWeights);
	}

	return true;
}

// ---------------------------------------------------------------------------
// instance
// ---------------------------------------------------------------------------

FAnimInstanceProxy* UMorphRigAnimInstance::CreateAnimInstanceProxy()
{
	return new FMorphRigAnimProxy();
}

void UMorphRigAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy)
{
	delete static_cast<FMorphRigAnimProxy*>(InProxy);
}

void UMorphRigAnimInstance::NativeInitializeAnimation()
{
	Super::NativeInitializeAnimation();

	// The four dash clips carry root motion, the capsule follows them.
	RootMotionMode = ERootMotionMode::RootMotionFromEverything;
}

void UMorphRigAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
	const double Start = FPlatformTime::Seconds();

	Super::NativeUpdateAnimation(DeltaSeconds);

	FMorphRigFrameBreakdown::Current().Animation =
		(FPlatformTime::Seconds() - Start) * 1000.0;
}

void UMorphRigAnimInstance::SetTeamColor(FLinearColor InColor)
{
	TeamColor = InColor;
}

void UMorphRigAnimInstance::SetState(EMorphRigState InState)
{
	State = InState;
}

void UMorphRigAnimInstance::ApplyBaseSequence(UAnimSequenceBase* Sequence, bool bLoop)
{
	BaseSequence = Sequence;
	bBaseLoop = bLoop;
}

void UMorphRigAnimInstance::ApplyActionSequence(UAnimSequenceBase* Sequence)
{
	ActionSequence = Sequence;
}

void UMorphRigAnimInstance::ApplyAimSequence(UAnimSequenceBase* Sequence)
{
	AimSequence = Sequence;
}

void UMorphRigAnimInstance::ApplyActionWeight(float Weight)
{
	ActionWeight = FMath::Clamp(Weight, 0.0f, 1.0f);
}

void UMorphRigAnimInstance::ApplyAimWeight(float Weight)
{
	AimWeight = FMath::Clamp(Weight, 0.0f, 1.0f);
}

float UMorphRigAnimInstance::GetBaseTime() const
{
	return GetProxyOnGameThread<FMorphRigAnimProxy>().BasePlayer.GetCurrentAssetTime();
}

float UMorphRigAnimInstance::GetBaseLength() const
{
	return GetProxyOnGameThread<FMorphRigAnimProxy>().BasePlayer.GetCurrentAssetLength();
}
