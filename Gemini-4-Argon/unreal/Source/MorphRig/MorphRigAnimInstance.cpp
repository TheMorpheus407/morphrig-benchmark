#include "MorphRigAnimInstance.h"
#include "Animation/AnimationPoseData.h"
#include "BonePose.h"

UMorphRigAnimInstance::UMorphRigAnimInstance()
{
}

void UMorphRigAnimInstance::TransitionToBaseAnim(UAnimSequence* NewSeq, bool bLoop, float BlendDuration, double StartTime)
{
	if (!NewSeq)
	{
		return;
	}
	if (CurrentBaseSeq == NewSeq && bCurrentBaseLoop == bLoop && StartTime == 0.0 && CrossfadeElapsed >= CrossfadeDuration)
	{
		return;
	}

	// Preserve the exact midpoint timestamp of the outgoing animation so interruptions NEVER snap to frame 0!
	if (CurrentBaseSeq)
	{
		PrevBaseSeq = CurrentBaseSeq;
		PrevBaseTime = CurrentBaseTime;
	}
	CurrentBaseSeq = NewSeq;
	CurrentBaseTime = StartTime;
	bCurrentBaseLoop = bLoop;
	CrossfadeDuration = FMath::Max(0.01f, BlendDuration);
	CrossfadeElapsed = (PrevBaseSeq != nullptr) ? 0.0f : CrossfadeDuration;
}

void UMorphRigAnimInstance::PlayUpperBodyAnim(UAnimSequence* NewUpperSeq, float BlendWeight)
{
	UpperBodySeq = NewUpperSeq;
	UpperBodyTime = 0.0;
	UpperBodyAlpha = NewUpperSeq ? FMath::Clamp(BlendWeight, 0.0f, 1.0f) : 0.0f;
}

void UMorphRigAnimInstance::PlayAdditiveHit(UAnimSequence* HitSeq, UAnimSequence* RefIdleSeq)
{
	HitAddSeq = HitSeq;
	HitRefSeq = RefIdleSeq;
	HitAddTime = 0.0;
	HitAddAlpha = HitSeq ? 1.0f : 0.0f;
}

void UMorphRigAnimInstance::AdvanceAnimations(float DeltaSeconds, float PlaybackRate)
{
	const float ScaledDt = DeltaSeconds * FMath::Clamp(PlaybackRate, 0.1f, 3.0f);

	if (CrossfadeElapsed < CrossfadeDuration)
	{
		CrossfadeElapsed = FMath::Min(CrossfadeDuration, CrossfadeElapsed + DeltaSeconds);
	}

	if (CurrentBaseSeq)
	{
		const double Len = FMath::Max(0.001, static_cast<double>(CurrentBaseSeq->GetPlayLength()));
		CurrentBaseTime += ScaledDt;
		if (bCurrentBaseLoop)
		{
			CurrentBaseTime = FMath::Fmod(CurrentBaseTime, Len);
		}
		else
		{
			CurrentBaseTime = FMath::Min(CurrentBaseTime, Len);
		}
	}

	if (LocoSeqA)
	{
		const double Len = FMath::Max(0.001, static_cast<double>(LocoSeqA->GetPlayLength()));
		LocoCycleTime = FMath::Fmod(LocoCycleTime + ScaledDt, Len);
	}

	if (UpperBodySeq && UpperBodyAlpha > 0.0f)
	{
		const double Len = FMath::Max(0.001, static_cast<double>(UpperBodySeq->GetPlayLength()));
		UpperBodyTime += ScaledDt;
		if (UpperBodyTime >= Len)
		{
			// Smoothly blend out at end of one-shot upper body clip
			UpperBodyAlpha = FMath::Max(0.0f, UpperBodyAlpha - DeltaSeconds * 6.0f);
			if (UpperBodyAlpha <= 0.001f)
			{
				UpperBodySeq = nullptr;
			}
		}
		else if (Len - UpperBodyTime < 0.12)
		{
			UpperBodyAlpha = static_cast<float>((Len - UpperBodyTime) / 0.12);
		}
	}

	if (HitAddSeq && HitAddAlpha > 0.0f)
	{
		const double Len = FMath::Max(0.001, static_cast<double>(HitAddSeq->GetPlayLength()));
		HitAddTime += ScaledDt;
		if (HitAddTime >= Len)
		{
			HitAddAlpha = 0.0f;
			HitAddSeq = nullptr;
		}
		else
		{
			HitAddAlpha = 1.0f - static_cast<float>(HitAddTime / Len);
		}
	}
}

void FMorphRigAnimInstanceProxy::PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds)
{
	FAnimInstanceProxy::PreUpdate(InAnimInstance, DeltaSeconds);

	UMorphRigAnimInstance* MR = Cast<UMorphRigAnimInstance>(InAnimInstance);
	if (!MR)
	{
		return;
	}

	CurrentBaseSeq = MR->CurrentBaseSeq;
	CurrentBaseTime = MR->CurrentBaseTime;
	PrevBaseSeq = MR->PrevBaseSeq;
	PrevBaseTime = MR->PrevBaseTime;
	CrossfadeAlpha = (MR->CrossfadeDuration > 0.0001f)
		? FMath::Clamp(MR->CrossfadeElapsed / MR->CrossfadeDuration, 0.0f, 1.0f)
		: 1.0f;

	bBlendLocomotion = MR->bBlendLocomotion;
	LocoSeqA = MR->LocoSeqA;
	LocoSeqB = MR->LocoSeqB;
	IdleSeq = MR->IdleSeq;
	LocoBlendAlpha = MR->LocoBlendAlpha;
	LocoSpeedAlpha = MR->LocoSpeedAlpha;
	LocoCycleTime = MR->LocoCycleTime;

	UpperBodySeq = MR->UpperBodySeq;
	UpperBodyTime = MR->UpperBodyTime;
	UpperBodyAlpha = MR->UpperBodyAlpha;

	HitAddSeq = MR->HitAddSeq;
	HitRefSeq = MR->HitRefSeq;
	HitAddTime = MR->HitAddTime;
	HitAddAlpha = MR->HitAddAlpha;

	bEnableAimOffset = MR->bEnableAimOffset;
	AimYaw = MR->AimYaw;
	AimPitch = MR->AimPitch;
	AimCenter = MR->AimCenter;
	AimUp = MR->AimUp;
	AimDown = MR->AimDown;
	AimLeft = MR->AimLeft;
	AimRight = MR->AimRight;

	DialogueSeq = MR->DialogueSeq;
	DialogueTime = MR->DialogueTime;
	DialogueAlpha = MR->DialogueAlpha;

	bEnableGroundIK = MR->bEnableGroundIK;
	PelvisOffsetZ = MR->PelvisOffsetZ;
	FootOffsetZ_L = MR->FootOffsetZ_L;
	FootOffsetZ_R = MR->FootOffsetZ_R;
	FootPitchDeg_L = MR->FootPitchDeg_L;
	FootPitchDeg_R = MR->FootPitchDeg_R;

	GazeYawDeg = MR->GazeYawDeg;
	GazePitchDeg = MR->GazePitchDeg;
	ManualJawOpen = MR->ManualJawOpen;
	ManualBlinkL = MR->ManualBlinkL;
	ManualBlinkR = MR->ManualBlinkR;
	ActiveExpressionMorph = MR->ActiveExpressionMorph;
	ActiveExpressionWeight = MR->ActiveExpressionWeight;
}

static void BlendPosesInPlace(FPoseContext& Dest, const FPoseContext& Src, float Weight)
{
	const float W = FMath::Clamp(Weight, 0.0f, 1.0f);
	if (W <= 0.0001f)
	{
		return;
	}
	for (FCompactPoseBoneIndex BoneIndex : Dest.Pose.ForEachBoneIndex())
	{
		FTransform& A = Dest.Pose[BoneIndex];
		const FTransform& B = Src.Pose[BoneIndex];
		A.SetTranslation(FMath::Lerp(A.GetTranslation(), B.GetTranslation(), W));
		A.SetRotation(FQuat::Slerp(A.GetRotation(), B.GetRotation(), W));
		A.SetScale3D(FMath::Lerp(A.GetScale3D(), B.GetScale3D(), W));
		A.NormalizeRotation();
	}
	Dest.Curve.LerpTo(Src.Curve, W);
}

static bool IsBoneDescendantOf(const FBoneContainer& BoneContainer, FCompactPoseBoneIndex BoneIdx, FCompactPoseBoneIndex RootFilterIdx)
{
	if (!RootFilterIdx.IsValid())
	{
		return false;
	}
	FCompactPoseBoneIndex Curr = BoneIdx;
	while (Curr.IsValid())
	{
		if (Curr == RootFilterIdx)
		{
			return true;
		}
		Curr = BoneContainer.GetParentBoneIndex(Curr);
	}
	return false;
}

bool FMorphRigAnimInstanceProxy::Evaluate(FPoseContext& Output)
{
	Output.ResetToRefPose();
	const FBoneContainer& BoneContainer = Output.Pose.GetBoneContainer();
	const FReferenceSkeleton& RefSkel = BoneContainer.GetReferenceSkeleton();

	// 1. Evaluate Base Layer (8-Way Locomotion Blend OR Single Action with Midpoint Crossfade)
	if (bBlendLocomotion && LocoSeqA && IdleSeq)
	{
		FAnimationPoseData IdleData(Output);
		FAnimExtractContext IdleCtx(LocoCycleTime, false);
		IdleSeq->GetAnimationPose(IdleData, IdleCtx);

		if (LocoSpeedAlpha > 0.001f)
		{
			FPoseContext MovePoseA(this);
			MovePoseA.ResetToRefPose();
			FAnimationPoseData DataA(MovePoseA);
			const double TimeA = FMath::Clamp(LocoCycleTime, 0.0, static_cast<double>(LocoSeqA->GetPlayLength()));
			FAnimExtractContext CtxA(TimeA, false);
			LocoSeqA->GetAnimationPose(DataA, CtxA);

			if (LocoSeqB && LocoBlendAlpha > 0.001f)
			{
				FPoseContext MovePoseB(this);
				MovePoseB.ResetToRefPose();
				FAnimationPoseData DataB(MovePoseB);
				const double TimeB = FMath::Clamp(LocoCycleTime, 0.0, static_cast<double>(LocoSeqB->GetPlayLength()));
				FAnimExtractContext CtxB(TimeB, false);
				LocoSeqB->GetAnimationPose(DataB, CtxB);
				BlendPosesInPlace(MovePoseA, MovePoseB, LocoBlendAlpha);
			}
			BlendPosesInPlace(Output, MovePoseA, LocoSpeedAlpha);
		}
	}
	else if (CurrentBaseSeq)
	{
		FAnimationPoseData BaseData(Output);
		const double ClampedTime = FMath::Clamp(CurrentBaseTime, 0.0, static_cast<double>(CurrentBaseSeq->GetPlayLength()));
		FAnimExtractContext BaseCtx(ClampedTime, false);
		CurrentBaseSeq->GetAnimationPose(BaseData, BaseCtx);

		// Crossfade from PrevBaseSeq at its exact interrupted midpoint (prevents frame-0 snapping!)
		if (PrevBaseSeq && CrossfadeAlpha < 0.999f)
		{
			FPoseContext PrevPose(this);
			PrevPose.ResetToRefPose();
			FAnimationPoseData PrevData(PrevPose);
			const double ClampedPrev = FMath::Clamp(PrevBaseTime, 0.0, static_cast<double>(PrevBaseSeq->GetPlayLength()));
			FAnimExtractContext PrevCtx(ClampedPrev, false);
			PrevBaseSeq->GetAnimationPose(PrevData, PrevCtx);

			BlendPosesInPlace(Output, PrevPose, 1.0f - CrossfadeAlpha);
		}
	}

	// Lookup key bone indices
	const int32 Spine01MeshIdx = RefSkel.FindBoneIndex(TEXT("spine_01"));
	const FCompactPoseBoneIndex Spine01Idx = BoneContainer.GetCompactPoseIndexFromSkeletonIndex(Spine01MeshIdx);
	const int32 HeadMeshIdx = RefSkel.FindBoneIndex(TEXT("head"));
	const FCompactPoseBoneIndex HeadIdx = BoneContainer.GetCompactPoseIndexFromSkeletonIndex(HeadMeshIdx);

	// 2. Upper-Body Layer (blends onto spine_01 and all descendant bones so legs continue locomotion)
	if (UpperBodySeq && UpperBodyAlpha > 0.001f && Spine01Idx.IsValid())
	{
		FPoseContext UpperPose(this);
		UpperPose.ResetToRefPose();
		FAnimationPoseData UpperData(UpperPose);
		const double ClampedUpper = FMath::Clamp(UpperBodyTime, 0.0, static_cast<double>(UpperBodySeq->GetPlayLength()));
		FAnimExtractContext UpperCtx(ClampedUpper, false);
		UpperBodySeq->GetAnimationPose(UpperData, UpperCtx);

		const float W = FMath::Clamp(UpperBodyAlpha, 0.0f, 1.0f);
		for (FCompactPoseBoneIndex BoneIdx : Output.Pose.ForEachBoneIndex())
		{
			if (IsBoneDescendantOf(BoneContainer, BoneIdx, Spine01Idx))
			{
				FTransform& A = Output.Pose[BoneIdx];
				const FTransform& B = UpperPose.Pose[BoneIdx];
				A.SetTranslation(FMath::Lerp(A.GetTranslation(), B.GetTranslation(), W));
				A.SetRotation(FQuat::Slerp(A.GetRotation(), B.GetRotation(), W));
				A.SetScale3D(FMath::Lerp(A.GetScale3D(), B.GetScale3D(), W));
				A.NormalizeRotation();
			}
		}
	}

	// 3. 9-Point Aim Offset Grid (additive delta relative to aim_level_center on upper body)
	if (bEnableAimOffset && AimCenter && Spine01Idx.IsValid() &&
		(FMath::Abs(AimYaw) > 0.5f || FMath::Abs(AimPitch) > 0.5f))
	{
		FPoseContext CenterPose(this);
		CenterPose.ResetToRefPose();
		FAnimationPoseData CenterData(CenterPose);
		FAnimExtractContext ZeroCtx(0.0, false);
		AimCenter->GetAnimationPose(CenterData, ZeroCtx);

		const float YawWeight = FMath::Clamp(FMath::Abs(AimYaw) / 60.0f, 0.0f, 1.0f);
		const float PitchWeight = FMath::Clamp(FMath::Abs(AimPitch) / 45.0f, 0.0f, 1.0f);
		UAnimSequence* YawSeq = (AimYaw >= 0.0f) ? AimRight : AimLeft;
		UAnimSequence* PitchSeq = (AimPitch >= 0.0f) ? AimUp : AimDown;

		FPoseContext YawPose(this);
		if (YawSeq && YawWeight > 0.01f)
		{
			YawPose.ResetToRefPose();
			FAnimationPoseData YawData(YawPose);
			YawSeq->GetAnimationPose(YawData, ZeroCtx);
		}

		FPoseContext PitchPose(this);
		if (PitchSeq && PitchWeight > 0.01f)
		{
			PitchPose.ResetToRefPose();
			FAnimationPoseData PitchData(PitchPose);
			PitchSeq->GetAnimationPose(PitchData, ZeroCtx);
		}

		for (FCompactPoseBoneIndex BoneIdx : Output.Pose.ForEachBoneIndex())
		{
			if (IsBoneDescendantOf(BoneContainer, BoneIdx, Spine01Idx))
			{
				const FQuat InvRef = CenterPose.Pose[BoneIdx].GetRotation().Inverse();
				FQuat CombinedDelta = FQuat::Identity;
				if (YawSeq && YawWeight > 0.01f)
				{
					const FQuat YawDelta = YawPose.Pose[BoneIdx].GetRotation() * InvRef;
					CombinedDelta = FQuat::Slerp(FQuat::Identity, YawDelta, YawWeight) * CombinedDelta;
				}
				if (PitchSeq && PitchWeight > 0.01f)
				{
					const FQuat PitchDelta = PitchPose.Pose[BoneIdx].GetRotation() * InvRef;
					CombinedDelta = FQuat::Slerp(FQuat::Identity, PitchDelta, PitchWeight) * CombinedDelta;
				}
				FTransform& A = Output.Pose[BoneIdx];
				A.SetRotation(CombinedDelta * A.GetRotation());
				A.NormalizeRotation();
			}
		}
	}

	// 4. Additive Hit-Reaction Layer (layers over upper body without snapping planted feet)
	if (HitAddSeq && HitRefSeq && HitAddAlpha > 0.001f && Spine01Idx.IsValid())
	{
		FPoseContext HitPose(this);
		HitPose.ResetToRefPose();
		FAnimationPoseData HitData(HitPose);
		const double ClampedHit = FMath::Clamp(HitAddTime, 0.0, static_cast<double>(HitAddSeq->GetPlayLength()));
		FAnimExtractContext HitCtx(ClampedHit, false);
		HitAddSeq->GetAnimationPose(HitData, HitCtx);

		FPoseContext RefPose(this);
		RefPose.ResetToRefPose();
		FAnimationPoseData RefData(RefPose);
		FAnimExtractContext ZeroCtx(0.0, false);
		HitRefSeq->GetAnimationPose(RefData, ZeroCtx);

		const float W = FMath::Clamp(HitAddAlpha, 0.0f, 1.0f);
		for (FCompactPoseBoneIndex BoneIdx : Output.Pose.ForEachBoneIndex())
		{
			if (IsBoneDescendantOf(BoneContainer, BoneIdx, Spine01Idx))
			{
				const FQuat DeltaRot = HitPose.Pose[BoneIdx].GetRotation() * RefPose.Pose[BoneIdx].GetRotation().Inverse();
				FTransform& A = Output.Pose[BoneIdx];
				A.SetRotation(FQuat::Slerp(FQuat::Identity, DeltaRot, W) * A.GetRotation());
				A.NormalizeRotation();
			}
		}
	}

	// 5. Spoken Dialogue Facial Layer (overrides head/facial bones + viseme morph curves during speech)
	if (DialogueSeq && DialogueAlpha > 0.001f && HeadIdx.IsValid())
	{
		FPoseContext DiagPose(this);
		DiagPose.ResetToRefPose();
		FAnimationPoseData DiagData(DiagPose);
		const double ClampedDiag = FMath::Clamp(DialogueTime, 0.0, static_cast<double>(DialogueSeq->GetPlayLength()));
		FAnimExtractContext DiagCtx(ClampedDiag, false);
		DialogueSeq->GetAnimationPose(DiagData, DiagCtx);

		const float W = FMath::Clamp(DialogueAlpha, 0.0f, 1.0f);
		for (FCompactPoseBoneIndex BoneIdx : Output.Pose.ForEachBoneIndex())
		{
			if (IsBoneDescendantOf(BoneContainer, BoneIdx, HeadIdx))
			{
				FTransform& A = Output.Pose[BoneIdx];
				const FTransform& B = DiagPose.Pose[BoneIdx];
				A.SetTranslation(FMath::Lerp(A.GetTranslation(), B.GetTranslation(), W));
				A.SetRotation(FQuat::Slerp(A.GetRotation(), B.GetRotation(), W));
				A.NormalizeRotation();
			}
		}
		Output.Curve.LerpTo(DiagPose.Curve, W);
	}

	// 6. Interactive Facial & Gaze Overrides (eye darts, blinks, jaw open, expression preset morphs)
	if (FMath::Abs(GazeYawDeg) > 0.05f || FMath::Abs(GazePitchDeg) > 0.05f)
	{
		const FQuat EyeDelta(FRotator(GazePitchDeg, GazeYawDeg, 0.0f));
		for (const TCHAR* EyeName : { TEXT("eye_l"), TEXT("eye_r") })
		{
			const int32 EyeMeshIdx = RefSkel.FindBoneIndex(EyeName);
			const FCompactPoseBoneIndex EyeIdx = BoneContainer.GetCompactPoseIndexFromSkeletonIndex(EyeMeshIdx);
			if (EyeIdx.IsValid())
			{
				Output.Pose[EyeIdx].SetRotation(Output.Pose[EyeIdx].GetRotation() * EyeDelta);
				Output.Pose[EyeIdx].NormalizeRotation();
			}
		}
	}
	if (ManualJawOpen > 0.001f)
	{
		Output.Curve.Set(FName(TEXT("jaw_open")), ManualJawOpen);
	}
	if (ManualBlinkL > 0.001f)
	{
		Output.Curve.Set(FName(TEXT("blink_l")), ManualBlinkL);
	}
	if (ManualBlinkR > 0.001f)
	{
		Output.Curve.Set(FName(TEXT("blink_r")), ManualBlinkR);
	}
	if (!ActiveExpressionMorph.IsNone() && ActiveExpressionWeight > 0.001f)
	{
		Output.Curve.Set(ActiveExpressionMorph, ActiveExpressionWeight);
	}

	// 7. Ground Adaptation (20-deg Slope & 20 cm Step Pelvis + Leg/Foot IK Adjustment)
	if (bEnableGroundIK &&
		(FMath::Abs(PelvisOffsetZ) > 0.05f || FMath::Abs(FootOffsetZ_L) > 0.05f || FMath::Abs(FootOffsetZ_R) > 0.05f))
	{
		const int32 PelvisMeshIdx = RefSkel.FindBoneIndex(TEXT("pelvis"));
		const FCompactPoseBoneIndex PelvisIdx = BoneContainer.GetCompactPoseIndexFromSkeletonIndex(PelvisMeshIdx);
		if (PelvisIdx.IsValid())
		{
			FVector PelvisTrans = Output.Pose[PelvisIdx].GetTranslation();
			// Convert cm offset to skeleton units if needed (1.0 in UE cm or 0.01 in m)
			const float UnitScale = (PelvisTrans.Size() < 5.0f) ? 0.01f : 1.0f;
			PelvisTrans.Z += PelvisOffsetZ * UnitScale;
			Output.Pose[PelvisIdx].SetTranslation(PelvisTrans);
		}

		// Apply knee flexion compensation & ankle pitch for raised foot on slope/step
		auto ApplyLegAdaptation = [&](const TCHAR* ThighName, const TCHAR* CalfName, const TCHAR* FootName, float FootDz, float PitchDeg)
		{
			const float RelRaiseCm = FMath::Clamp(FootDz - PelvisOffsetZ, 0.0f, 25.0f);
			const float KneeFlexDeg = (RelRaiseCm / 20.0f) * 34.0f;

			const FCompactPoseBoneIndex ThighIdx = BoneContainer.GetCompactPoseIndexFromSkeletonIndex(RefSkel.FindBoneIndex(ThighName));
			const FCompactPoseBoneIndex CalfIdx = BoneContainer.GetCompactPoseIndexFromSkeletonIndex(RefSkel.FindBoneIndex(CalfName));
			const FCompactPoseBoneIndex FootIdx = BoneContainer.GetCompactPoseIndexFromSkeletonIndex(RefSkel.FindBoneIndex(FootName));

			if (ThighIdx.IsValid() && KneeFlexDeg > 0.1f)
			{
				const FQuat ThighFlex(FVector(1.0f, 0.0f, 0.0f), FMath::DegreesToRadians(-KneeFlexDeg * 0.55f));
				Output.Pose[ThighIdx].SetRotation(ThighFlex * Output.Pose[ThighIdx].GetRotation());
				Output.Pose[ThighIdx].NormalizeRotation();
			}
			if (CalfIdx.IsValid() && KneeFlexDeg > 0.1f)
			{
				const FQuat CalfFlex(FVector(1.0f, 0.0f, 0.0f), FMath::DegreesToRadians(KneeFlexDeg));
				Output.Pose[CalfIdx].SetRotation(CalfFlex * Output.Pose[CalfIdx].GetRotation());
				Output.Pose[CalfIdx].NormalizeRotation();
			}
			if (FootIdx.IsValid())
			{
				const float TotalFootPitch = PitchDeg - KneeFlexDeg * 0.45f;
				const FQuat AnkleRot(FVector(1.0f, 0.0f, 0.0f), FMath::DegreesToRadians(TotalFootPitch));
				Output.Pose[FootIdx].SetRotation(AnkleRot * Output.Pose[FootIdx].GetRotation());
				Output.Pose[FootIdx].NormalizeRotation();
			}
		};

		ApplyLegAdaptation(TEXT("thigh_l"), TEXT("calf_l"), TEXT("foot_l"), FootOffsetZ_L, FootPitchDeg_L);
		ApplyLegAdaptation(TEXT("thigh_r"), TEXT("calf_r"), TEXT("foot_r"), FootOffsetZ_R, FootPitchDeg_R);
	}

	return true;
}
