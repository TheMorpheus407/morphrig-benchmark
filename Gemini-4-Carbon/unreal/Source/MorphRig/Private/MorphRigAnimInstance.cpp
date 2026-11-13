#include "MorphRigAnimInstance.h"
#include "MorphRigGeneratedMeta.h"
#include "Animation/AnimationPoseData.h"
#include "AnimationRuntime.h"
#include "BonePose.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/Character.h"
#include "Engine/World.h"

namespace
{
	void BlendPoseInPlace(FCompactPose& BasePose, const FCompactPose& TargetPose, float Alpha)
	{
		const float ClampedAlpha = FMath::Clamp(Alpha, 0.0f, 1.0f);
		if (ClampedAlpha <= KINDA_SMALL_NUMBER)
		{
			return;
		}
		if (ClampedAlpha >= 1.0f - KINDA_SMALL_NUMBER)
		{
			BasePose.CopyBonesFrom(TargetPose);
			return;
		}
		for (FCompactPoseBoneIndex BoneIdx : BasePose.ForEachBoneIndex())
		{
			FTransform& A = BasePose[BoneIdx];
			const FTransform& B = TargetPose[BoneIdx];
			FQuat QA = A.GetRotation();
			FQuat QB = B.GetRotation();
			QB.EnforceShortestArcWith(QA);
			FQuat QOut = FQuat::Slerp(QA, QB, ClampedAlpha);
			QOut.Normalize();
			A.SetRotation(QOut);
			A.SetTranslation(FMath::Lerp(A.GetTranslation(), B.GetTranslation(), ClampedAlpha));
			A.SetScale3D(FMath::Lerp(A.GetScale3D(), B.GetScale3D(), ClampedAlpha));
		}
	}

	void BlendCurvesInPlace(TMap<FName, float>& BaseCurves, const TMap<FName, float>& TargetCurves, float Alpha)
	{
		const float W = FMath::Clamp(Alpha, 0.0f, 1.0f);
		if (W <= KINDA_SMALL_NUMBER)
		{
			return;
		}
		TSet<FName> Keys;
		for (const auto& KV : BaseCurves) { Keys.Add(KV.Key); }
		for (const auto& KV : TargetCurves) { Keys.Add(KV.Key); }
		for (const FName& K : Keys)
		{
			const float VA = BaseCurves.FindRef(K);
			const float VB = TargetCurves.FindRef(K);
			const float VOut = FMath::Lerp(VA, VB, W);
			if (FMath::Abs(VOut) > 1e-4f)
			{
				BaseCurves.Add(K, VOut);
			}
			else
			{
				BaseCurves.Remove(K);
			}
		}
	}

	void SolveAnalyticalTwoBoneIK_CS(
		FTransform& InOutRootCS,
		FTransform& InOutMidCS,
		FTransform& InOutEndCS,
		const FVector& DesiredEndPosCS,
		const FVector& FallbackBendPoleDirCS)
	{
		const FVector RootPos = InOutRootCS.GetLocation();
		const FVector MidPos = InOutMidCS.GetLocation();
		const FVector EndPos = InOutEndCS.GetLocation();

		const float L1 = (MidPos - RootPos).Size();
		const float L2 = (EndPos - MidPos).Size();
		if (L1 < 1.0f || L2 < 1.0f)
		{
			return;
		}

		const FVector OrigRootToEnd = EndPos - RootPos;
		const float OrigDist = OrigRootToEnd.Size();
		const FVector ToTarget = DesiredEndPosCS - RootPos;
		const float RawTargetDist = ToTarget.Size();
		if (OrigDist < 1.0f || RawTargetDist < 1.0f)
		{
			return;
		}

		const float MinReach = FMath::Abs(L1 - L2) + 1.5f;
		const float MaxReach = (L1 + L2) * 0.997f;
		const float ClampedDist = FMath::Clamp(RawTargetDist, MinReach, MaxReach);

		// Preserve animated bend plane normal: (End - Root) x (Mid - Root)
		FVector BendPlaneNormal = FVector::CrossProduct(OrigRootToEnd, MidPos - RootPos);
		if (BendPlaneNormal.SizeSquared() < 1e-4f)
		{
			BendPlaneNormal = FVector::CrossProduct(OrigRootToEnd, FallbackBendPoleDirCS);
		}
		BendPlaneNormal = BendPlaneNormal.GetSafeNormal();
		if (BendPlaneNormal.IsNearlyZero())
		{
			BendPlaneNormal = FVector::RightVector;
		}

		// Law of cosines interior angles at hip/thigh root and knee/mid joint
		const float CosRoot0 = FMath::Clamp((L1 * L1 + OrigDist * OrigDist - L2 * L2) / (2.0f * L1 * OrigDist), -1.0f, 1.0f);
		const float CosRoot1 = FMath::Clamp((L1 * L1 + ClampedDist * ClampedDist - L2 * L2) / (2.0f * L1 * ClampedDist), -1.0f, 1.0f);
		const float AngleRoot0 = FMath::Acos(CosRoot0);
		const float AngleRoot1 = FMath::Acos(CosRoot1);
		const float DeltaRootAngle = AngleRoot1 - AngleRoot0;

		const FQuat RootFlexQ(BendPlaneNormal, DeltaRootAngle);
		FQuat NewRootRot = RootFlexQ * InOutRootCS.GetRotation();
		NewRootRot.Normalize();

		const FVector FlexedMidPos = RootPos + RootFlexQ.RotateVector(MidPos - RootPos);
		const FVector DesiredEndAlongOrigRay = RootPos + OrigRootToEnd.GetSafeNormal() * ClampedDist;

		const FVector OldMidToEndDir = (EndPos - MidPos).GetSafeNormal();
		const FVector FlexedMidToEndDir = (DesiredEndAlongOrigRay - FlexedMidPos).GetSafeNormal();
		const FQuat MidFlexQ = FQuat::FindBetweenNormals(OldMidToEndDir, FlexedMidToEndDir);
		FQuat NewMidRot = MidFlexQ * InOutMidCS.GetRotation();
		NewMidRot.Normalize();

		// Swing entire leg plane from OrigRootToEnd direction to ToTarget direction
		const FQuat SwingQ = FQuat::FindBetweenNormals(OrigRootToEnd.GetSafeNormal(), ToTarget.GetSafeNormal());
		NewRootRot = SwingQ * NewRootRot;
		NewRootRot.Normalize();
		NewMidRot = SwingQ * NewMidRot;
		NewMidRot.Normalize();

		const FVector FinalMidPos = RootPos + SwingQ.RotateVector(FlexedMidPos - RootPos);
		const FVector FinalEndPos = RootPos + ToTarget.GetSafeNormal() * ClampedDist;

		InOutRootCS.SetRotation(NewRootRot);
		InOutMidCS.SetLocation(FinalMidPos);
		InOutMidCS.SetRotation(NewMidRot);
		InOutEndCS.SetLocation(FinalEndPos);
	}
}

// ============================================================================
// FMorphRigAnimInstanceProxy
// ============================================================================

FMorphRigAnimInstanceProxy::FMorphRigAnimInstanceProxy(UAnimInstance* InAnimInstance)
	: FAnimInstanceProxy(InAnimInstance)
{
	for (int32 i = 0; i < GMorphRigClipCount; ++i)
	{
		MetaIndexMap.Add(FName(GMorphRigClips[i].ClipId), i);
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

	if (SequenceMap.Num() != MR->LoadedSequences.Num())
	{
		SequenceMap.Reset();
		for (const auto& KV : MR->LoadedSequences)
		{
			SequenceMap.Add(KV.Key, KV.Value.Get());
		}
	}

	PrimaryState = MR->PrimaryState;
	PrimaryClip = MR->PrimaryClip;
	PrimaryTime = MR->PrimaryTime;
	bPrimaryLoop = MR->bPrimaryLoop;
	// Dash root motion moves the Actor Capsule on the Game Thread, so zero mesh-local root XY to prevent double travel!
	bZeroRootXY = (MR->PrimaryState == EMorphRigPrimaryState::MobilityDash);

	LocoOverrideClip = MR->LocoSubClip;
	LocoOverrideTime = MR->LocoSubTime;
	LocoOverrideWeight = MR->LocoSubWeight;
	bLocoOverrideLoop = MR->bLocoSubLoop;

	LocalVelForward = MR->LocalVelForward;
	LocalVelRight = MR->LocalVelRight;
	GroundSpeed = MR->GroundSpeed;
	GaitPhase = MR->GaitPhase;
	bCombatStance = MR->bCombatStance;
	bWounded = MR->bWounded;
	bFear = MR->bFeared;
	bCharm = MR->bCharmed;
	bTaunt = MR->bTaunted;
	bStasis = MR->bStasis;

	UpperClip = MR->UpperClip;
	UpperTime = MR->UpperTime;
	UpperWeight = MR->UpperWeight;

	bEnableAim = MR->bEnableAim;
	AimYawDeg = MR->AimYawDeg;
	AimPitchDeg = MR->AimPitchDeg;
	const float ReloadSuppression = (UpperClip == TEXT("reload")) ? FMath::Clamp(1.0f - UpperWeight, 0.0f, 1.0f) : 1.0f;
	AimWeight = ((MR->PrimaryState == EMorphRigPrimaryState::Locomotion && LocoOverrideWeight < 0.75f) ? 1.0f : 0.0f) * ReloadSuppression;

	bEnableLookAt = MR->bEnableLookAt;
	if (USkeletalMeshComponent* SkelComp = MR->GetSkelMeshComponent())
	{
		LookAtTargetCS = SkelComp->GetComponentTransform().InverseTransformPosition(MR->LookAtTargetWorld);
	}

	HitClip = MR->HitClip;
	HitTime = MR->HitTime;
	HitWeight = MR->HitWeight;

	bEnableGroundIK = MR->bEnableGroundIK;
	const bool bGroundedLoco = (MR->PrimaryState == EMorphRigPrimaryState::Locomotion) && MR->bIsGrounded &&
		(LocoOverrideClip != TEXT("jump_start") && LocoOverrideClip != TEXT("jump_air") && LocoOverrideClip != TEXT("fall"));
	GroundIKWeight = (bEnableGroundIK && bGroundedLoco) ? 1.0f : 0.0f;
	FootOffsetZ_L = MR->FootOffsetZ_L;
	FootOffsetZ_R = MR->FootOffsetZ_R;
	PelvisOffsetZ = MR->PelvisOffsetZ;
	FootNormalCS_L = MR->FootNormalCS_L;
	FootNormalCS_R = MR->FootNormalCS_R;

	CableSpringRad = MR->CableSpringPos;
	StrapSpringRad = MR->StrapSpringPos;
	FaceManual = MR->FaceManual;

	bCaptureSnapshotThisFrame = MR->bPendingSnapshotCapture;
	MR->bPendingSnapshotCapture = false;

	if (MR->SnapshotCrossfadeElapsed < MR->SnapshotCrossfadeDuration && MR->SnapshotCrossfadeDuration > 1e-4f)
	{
		const float U = FMath::Clamp(MR->SnapshotCrossfadeElapsed / MR->SnapshotCrossfadeDuration, 0.0f, 1.0f);
		SnapshotAlpha = 1.0f - (U * U * (3.0f - 2.0f * U));
	}
	else
	{
		SnapshotAlpha = 0.0f;
	}
}

void FMorphRigAnimInstanceProxy::CacheBones()
{
	FAnimInstanceProxy::CacheBones();
	bAimGridCached = false;

	const FBoneContainer& BC = GetRequiredBones();
	if (!BC.IsValid())
	{
		return;
	}

	auto FindIdx = [&BC](const TCHAR* Name) -> FCompactPoseBoneIndex
	{
		const int32 SkelIdx = BC.GetPoseBoneIndexForBoneName(FName(Name));
		return (SkelIdx != INDEX_NONE) ? BC.MakeCompactPoseIndex(FMeshPoseBoneIndex(SkelIdx)) : FCompactPoseBoneIndex(INDEX_NONE);
	};

	RootIdx = FindIdx(TEXT("root"));
	PelvisIdx = FindIdx(TEXT("pelvis"));
	Spine01Idx = FindIdx(TEXT("spine_01"));
	Spine02Idx = FindIdx(TEXT("spine_02"));
	Spine03Idx = FindIdx(TEXT("spine_03"));
	NeckIdx = FindIdx(TEXT("neck_01"));
	HeadIdx = FindIdx(TEXT("head"));
	EyeLIdx = FindIdx(TEXT("eye_l"));
	EyeRIdx = FindIdx(TEXT("eye_r"));

	ThighLIdx = FindIdx(TEXT("thigh_l"));
	CalfLIdx = FindIdx(TEXT("calf_l"));
	FootLIdx = FindIdx(TEXT("foot_l"));
	ThighRIdx = FindIdx(TEXT("thigh_r"));
	CalfRIdx = FindIdx(TEXT("calf_r"));
	FootRIdx = FindIdx(TEXT("foot_r"));

	CableIdx[0] = FindIdx(TEXT("cable_01"));
	CableIdx[1] = FindIdx(TEXT("cable_02"));
	CableIdx[2] = FindIdx(TEXT("cable_03"));
	StrapIdx[0] = FindIdx(TEXT("strap_01"));
	StrapIdx[1] = FindIdx(TEXT("strap_02"));
	StrapIdx[2] = FindIdx(TEXT("strap_03"));
	EmitterBoneRIdx = FindIdx(TEXT("emitter_bone_r"));
	CellBoneIdx = FindIdx(TEXT("cell_bone"));
	BeaconBoneIdx = FindIdx(TEXT("beacon_bone"));

	// Auto-detect exact RefSkeleton root scale (e.g. 100x from Blender FBX), mesh-space axes, and docked prop relative transforms
	if (const USkeleton* Skel = GetSkeleton())
	{
		const FReferenceSkeleton& RefSkel = Skel->GetReferenceSkeleton();
		if (RefSkel.GetNum() > 0)
		{
			const FVector CandScale = RefSkel.GetRefBonePose()[0].GetScale3D();
			if (!CandScale.IsNearlyZero())
			{
				RefRootScale = CandScale;
			}
		}

		auto CalcCS = [&RefSkel](int32 Idx) -> FTransform
		{
			FTransform Acc = FTransform::Identity;
			int32 Cur = Idx;
			while (Cur != INDEX_NONE)
			{
				Acc = Acc * RefSkel.GetRefBonePose()[Cur];
				Cur = RefSkel.GetParentIndex(Cur);
			}
			return Acc;
		};

		const int32 FootRef = RefSkel.FindBoneIndex(TEXT("foot_l"));
		const int32 BallRef = RefSkel.FindBoneIndex(TEXT("ball_l"));
		if (FootRef != INDEX_NONE && BallRef != INDEX_NONE)
		{
			FVector ToeVec = CalcCS(BallRef).GetLocation() - CalcCS(FootRef).GetLocation();
			ToeVec.Z = 0.0f;
			if (!ToeVec.IsNearlyZero())
			{
				MeshForwardCS = ToeVec.GetSafeNormal();
				// In Unreal left-handed (+X fwd, +Y right, +Z up), Up x Forward = Right, Forward x Up = Left
				MeshLeftCS = FVector::CrossProduct(MeshForwardCS, FVector::UpVector).GetSafeNormal();
			}
		}

		const int32 EmitterRef = RefSkel.FindBoneIndex(TEXT("emitter_bone_r"));
		const int32 CellRef = RefSkel.FindBoneIndex(TEXT("cell_bone"));
		if (EmitterRef != INDEX_NONE && CellRef != INDEX_NONE)
		{
			RefCellInEmitter = CalcCS(CellRef).GetRelativeTransform(CalcCS(EmitterRef));
		}

		const int32 PelvisRef = RefSkel.FindBoneIndex(TEXT("pelvis"));
		const int32 BeaconRef = RefSkel.FindBoneIndex(TEXT("beacon_bone"));
		if (PelvisRef != INDEX_NONE && BeaconRef != INDEX_NONE)
		{
			RefBeaconInPelvis = CalcCS(BeaconRef).GetRelativeTransform(CalcCS(PelvisRef));
		}
	}

	// Build UpperBodyMask: true for spine_01 and every descendant of spine_01
	const int32 NumCompact = BC.GetCompactPoseNumBones();
	UpperBodyMask.Init(false, NumCompact);
	if (Spine01Idx.IsValid())
	{
		UpperBodyMask[Spine01Idx.GetInt()] = true;
		for (int32 i = 0; i < NumCompact; ++i)
		{
			FCompactPoseBoneIndex Cur(i);
			FCompactPoseBoneIndex Par = BC.GetParentBoneIndex(Cur);
			while (Par.IsValid())
			{
				if (Par == Spine01Idx)
				{
					UpperBodyMask[i] = true;
					break;
				}
				Par = BC.GetParentBoneIndex(Par);
			}
		}
	}
}

void FMorphRigAnimInstanceProxy::SampleClipPoseAndCurves(
	FName ClipName,
	float SampleTime,
	bool bLoop,
	FPoseContext& OutPoseCtx,
	TMap<FName, float>& OutCurves,
	bool bZeroMeshRootXY) const
{
	OutPoseCtx.ResetToRefPose();
	OutCurves.Reset();

	UAnimSequence* const* FoundSeq = SequenceMap.Find(ClipName);
	if (FoundSeq && *FoundSeq)
	{
		const UAnimSequence* Seq = *FoundSeq;
		const float SeqLen = FMath::Max(0.001f, Seq->GetPlayLength());
		float EvalT = SampleTime;
		if (bLoop && SeqLen > 0.001f)
		{
			EvalT = FMath::Fmod(SampleTime, SeqLen);
			if (EvalT < 0.0f) { EvalT += SeqLen; }
		}
		else
		{
			EvalT = FMath::Clamp(SampleTime, 0.0f, SeqLen);
		}

		FAnimExtractContext ExtractCtx(static_cast<double>(EvalT), false, FDeltaTimeRecord(0.0f), bLoop);
		if (Seq->IsValidAdditive() && ClipName != TEXT("idle_combat"))
		{
			// Evaluate full-scale idle_combat(0) base pose, then accumulate local-space additive hit delta cleanly
			TMap<FName, float> BaseCurves;
			SampleClipPoseAndCurves(TEXT("idle_combat"), 0.0f, false, OutPoseCtx, BaseCurves, false);

			FPoseContext AddCtx(OutPoseCtx);
			AddCtx.ResetToAdditiveIdentity();
			FAnimationPoseData AddPoseData(AddCtx);
			Seq->GetAnimationPose(AddPoseData, ExtractCtx);

			FAnimationPoseData BasePoseData(OutPoseCtx);
			FAnimationRuntime::AccumulateAdditivePose(BasePoseData, AddPoseData, 1.0f, Seq->GetAdditiveAnimType());
			OutPoseCtx.Pose.NormalizeRotations();

			AddCtx.Curve.ForEachElement([&OutCurves](const UE::Anim::FCurveElement& Elem)
			{
				if (FMath::Abs(Elem.Value) > 1e-4f)
				{
					OutCurves.Add(Elem.Name, Elem.Value);
				}
			});
		}
		else
		{
			FAnimationPoseData PoseData(OutPoseCtx);
			Seq->GetAnimationPose(PoseData, ExtractCtx);

			OutPoseCtx.Curve.ForEachElement([&OutCurves](const UE::Anim::FCurveElement& Elem)
			{
				if (FMath::Abs(Elem.Value) > 1e-4f)
				{
					OutCurves.Add(Elem.Name, Elem.Value);
				}
			});

			if (RootIdx.IsValid())
			{
				FTransform RootT = OutPoseCtx.Pose[RootIdx];
				// Restore RefSkeleton root Scale3D (100,100,100) and convert ARMATURE-only FBX meter root translation to cm!
				FVector Loc = RootT.GetTranslation() * RefRootScale;
				if (bZeroMeshRootXY)
				{
					Loc.X = 0.0f;
					Loc.Y = 0.0f;
				}
				RootT.SetTranslation(Loc);
				RootT.SetScale3D(RefRootScale);
				OutPoseCtx.Pose[RootIdx] = RootT;
			}
		}
	}

	// Ensure 100% exact facial/viseme/corrective morph curves from compiled metadata table
	if (const int32* MetaIdxPtr = MetaIndexMap.Find(ClipName))
	{
		const FMorphRigClipMeta& Meta = GMorphRigClips[*MetaIdxPtr];
		const float Dur = FMath::Max(0.001f, Meta.DurationSec);
		float EvalT = bLoop ? FMath::Fmod(FMath::Max(0.0f, SampleTime), Dur) : FMath::Clamp(SampleTime, 0.0f, Dur);
		const float ExactFrame = EvalT * 30.0f;

		for (int32 c = 0; c < Meta.CurveTrackCount; ++c)
		{
			const FMorphRigCurveTrackMeta& Track = GMorphRigCurveTracks[Meta.CurveTrackOffset + c];
			if (Track.SampleCount <= 0) { continue; }
			const int32 F0 = FMath::Clamp(FMath::FloorToInt(ExactFrame), 0, Track.SampleCount - 1);
			const int32 F1 = FMath::Clamp(F0 + 1, 0, Track.SampleCount - 1);
			const float Frac = FMath::Clamp(ExactFrame - static_cast<float>(F0), 0.0f, 1.0f);
			const float Val = FMath::Lerp(
				GMorphRigCurveSamples[Track.SampleOffset + F0],
				GMorphRigCurveSamples[Track.SampleOffset + F1],
				Frac);
			if (FMath::Abs(Val) > 1e-4f)
			{
				OutCurves.Add(FName(Track.CurveName), Val);
			}
		}
	}
}

void FMorphRigAnimInstanceProxy::EvaluateLocomotionPose(FPoseContext& OutPoseCtx, TMap<FName, float>& OutCurves) const
{
	// 1. Evaluate Idle stance only when stationary or blending Idle -> Walk (<= 150 cm/s)
	const FName IdleClip = bWounded ? FName(TEXT("idle_wounded")) : (bCombatStance ? FName(TEXT("idle_combat")) : FName(TEXT("idle_relaxed")));
	if (GroundSpeed <= 150.0f)
	{
		SampleClipPoseAndCurves(IdleClip, PrimaryTime, true, OutPoseCtx, OutCurves);
	}

	// 2. If moving horizontally, evaluate phase-synchronized 8-direction walk/run/sprint
	if (GroundSpeed > 2.0f)
	{
		static const FName WalkDirs[8] = {
			TEXT("walk_b"), TEXT("walk_bl"), TEXT("walk_l"), TEXT("walk_fl"),
			TEXT("walk_f"), TEXT("walk_fr"), TEXT("walk_r"), TEXT("walk_br")
		};
		static const FName RunDirs[8] = {
			TEXT("run_b"), TEXT("run_bl"), TEXT("run_l"), TEXT("run_fl"),
			TEXT("run_f"), TEXT("run_fr"), TEXT("run_r"), TEXT("run_br")
		};

		// AngleDeg in [-180, +180]: -180=b(0), -135=bl(1), -90=l(2), -45=fl(3), 0=f(4), +45=fr(5), +90=r(6), +135=br(7), +180=b(0)
		const float AngleDeg = FMath::RadiansToDegrees(FMath::Atan2(LocalVelRight, LocalVelForward));
		const float SectorF = (AngleDeg + 180.0f) / 45.0f; // [0..8]
		const int32 Idx0 = FMath::FloorToInt(SectorF) % 8;
		const int32 SafeIdx0 = (Idx0 < 0) ? (Idx0 + 8) : Idx0;
		const int32 SafeIdx1 = (SafeIdx0 + 1) % 8;
		const float DirAlpha = FMath::Clamp(SectorF - FMath::FloorToFloat(SectorF), 0.0f, 1.0f);

		auto EvalOctantPair = [&](const FName DirTable[8], FPoseContext& DestCtx, TMap<FName, float>& DestCurves)
		{
			const FName C0 = DirTable[SafeIdx0];
			const FName C1 = DirTable[SafeIdx1];
			float Dur0 = 1.0f, Dur1 = 1.0f;
			if (const int32* M0 = MetaIndexMap.Find(C0)) { Dur0 = GMorphRigClips[*M0].DurationSec; }
			if (const int32* M1 = MetaIndexMap.Find(C1)) { Dur1 = GMorphRigClips[*M1].DurationSec; }

			SampleClipPoseAndCurves(C0, GaitPhase * Dur0, true, DestCtx, DestCurves);
			if (DirAlpha > 0.01f)
			{
				FPoseContext Ctx1(DestCtx);
				TMap<FName, float> Curves1;
				SampleClipPoseAndCurves(C1, GaitPhase * Dur1, true, Ctx1, Curves1);
				BlendPoseInPlace(DestCtx.Pose, Ctx1.Pose, DirAlpha);
				BlendCurvesInPlace(DestCurves, Curves1, DirAlpha);
			}
		};

		FPoseContext MoveCtx(OutPoseCtx);
		TMap<FName, float> MoveCurves;

		if (GroundSpeed <= 150.0f)
		{
			EvalOctantPair(WalkDirs, MoveCtx, MoveCurves);
			const float IdleToWalk = FMath::Clamp(GroundSpeed / 150.0f, 0.0f, 1.0f);
			BlendPoseInPlace(OutPoseCtx.Pose, MoveCtx.Pose, IdleToWalk);
			BlendCurvesInPlace(OutCurves, MoveCurves, IdleToWalk);
		}
		else if (GroundSpeed <= 400.0f)
		{
			EvalOctantPair(WalkDirs, OutPoseCtx, OutCurves);
			EvalOctantPair(RunDirs, MoveCtx, MoveCurves);
			const float WalkToRun = FMath::Clamp((GroundSpeed - 150.0f) / 250.0f, 0.0f, 1.0f);
			BlendPoseInPlace(OutPoseCtx.Pose, MoveCtx.Pose, WalkToRun);
			BlendCurvesInPlace(OutCurves, MoveCurves, WalkToRun);
		}
		else
		{
			EvalOctantPair(RunDirs, OutPoseCtx, OutCurves);
			const float ForwardFactor = FMath::Clamp(FMath::Cos(FMath::DegreesToRadians(AngleDeg)), 0.0f, 1.0f);
			const float RunToSprint = FMath::Clamp((GroundSpeed - 400.0f) / 250.0f, 0.0f, 1.0f) * ForwardFactor;
			if (RunToSprint > 0.01f)
			{
				float SprintDur = 0.6f;
				if (const int32* MS = MetaIndexMap.Find(TEXT("sprint_f"))) { SprintDur = GMorphRigClips[*MS].DurationSec; }
				SampleClipPoseAndCurves(TEXT("sprint_f"), GaitPhase * SprintDur, true, MoveCtx, MoveCurves);
				BlendPoseInPlace(OutPoseCtx.Pose, MoveCtx.Pose, RunToSprint);
				BlendCurvesInPlace(OutCurves, MoveCurves, RunToSprint);
			}
		}
	}

	// 3. Locomotion transition sub-clip (starts, stops, 90 turns, 180 pivots, jump/fall/land)
	if (LocoOverrideClip != NAME_None && LocoOverrideWeight > 0.01f)
	{
		FPoseContext SubCtx(OutPoseCtx);
		TMap<FName, float> SubCurves;
		SampleClipPoseAndCurves(LocoOverrideClip, LocoOverrideTime, bLocoOverrideLoop, SubCtx, SubCurves);
		BlendPoseInPlace(OutPoseCtx.Pose, SubCtx.Pose, LocoOverrideWeight);
		BlendCurvesInPlace(OutCurves, SubCurves, LocoOverrideWeight);
	}
}

void FMorphRigAnimInstanceProxy::ApplyAimGridLayer(FPoseContext& InOutPoseCtx, float YawDeg, float PitchDeg, float Weight) const
{
	const int32 NumPoseBones = InOutPoseCtx.Pose.GetNumBones();
	if (Weight <= 0.01f || UpperBodyMask.Num() != NumPoseBones)
	{
		return;
	}
	if (FMath::Abs(YawDeg) < 0.25f && FMath::Abs(PitchDeg) < 0.25f)
	{
		return;
	}

	static const FName Grid[3][3] = {
		{ TEXT("aim_down_left"),  TEXT("aim_down_center"),  TEXT("aim_down_right")  },
		{ TEXT("aim_level_left"), TEXT("aim_level_center"), TEXT("aim_level_right") },
		{ TEXT("aim_up_left"),    TEXT("aim_up_center"),    TEXT("aim_up_right")    }
	};

	if (!bAimGridCached || CachedAimCenter.Num() != NumPoseBones)
	{
		TMap<FName, float> DummyCurves;
		FPoseContext TmpCtx(InOutPoseCtx);
		auto CacheClipPose = [&](FName Clip, TArray<FTransform>& Dest)
		{
			SampleClipPoseAndCurves(Clip, 0.0f, false, TmpCtx, DummyCurves);
			Dest.SetNumUninitialized(NumPoseBones);
			for (int32 i = 0; i < NumPoseBones; ++i)
			{
				Dest[i] = TmpCtx.Pose[FCompactPoseBoneIndex(i)];
			}
		};
		CacheClipPose(TEXT("aim_level_center"), CachedAimCenter);
		for (int32 r = 0; r < 3; ++r)
		{
			for (int32 c = 0; c < 3; ++c)
			{
				CacheClipPose(Grid[r][c], CachedAimGrid[r][c]);
			}
		}
		bAimGridCached = true;
	}

	const float ClampedYaw = FMath::Clamp(YawDeg, -60.0f, 60.0f);
	const float ClampedPitch = FMath::Clamp(PitchDeg, -35.0f, 35.0f);

	const int32 Col0 = (ClampedYaw < 0.0f) ? 0 : 1;
	const int32 Col1 = Col0 + 1;
	const float AlphaYaw = (ClampedYaw < 0.0f) ? ((ClampedYaw + 60.0f) / 60.0f) : (ClampedYaw / 60.0f);

	const int32 Row0 = (ClampedPitch < 0.0f) ? 0 : 1;
	const int32 Row1 = Row0 + 1;
	const float AlphaPitch = (ClampedPitch < 0.0f) ? ((ClampedPitch + 35.0f) / 35.0f) : (ClampedPitch / 35.0f);

	// Apply upper-body bone-local rotation delta relative to cached aim_level_center so legs stay 100% planted!
	for (int32 i = 0; i < NumPoseBones; ++i)
	{
		if (!UpperBodyMask[i])
		{
			continue;
		}
		const FQuat& Q00 = CachedAimGrid[Row0][Col0][i].GetRotation();
		const FQuat& Q10 = CachedAimGrid[Row0][Col1][i].GetRotation();
		const FQuat& Q01 = CachedAimGrid[Row1][Col0][i].GetRotation();
		const FQuat& Q11 = CachedAimGrid[Row1][Col1][i].GetRotation();

		const FQuat QRow0 = FQuat::Slerp(Q00, Q10, AlphaYaw);
		const FQuat QRow1 = FQuat::Slerp(Q01, Q11, AlphaYaw);
		FQuat TargetQ = FQuat::Slerp(QRow0, QRow1, AlphaPitch);
		TargetQ.Normalize();

		const FQuat RefQ = CachedAimCenter[i].GetRotation();
		FQuat LocalDelta = RefQ.Inverse() * TargetQ;
		LocalDelta.EnforceShortestArcWith(FQuat::Identity);
		const FQuat WeightedDelta = FQuat::Slerp(FQuat::Identity, LocalDelta, Weight);

		const FCompactPoseBoneIndex BoneIdx(i);
		FQuat FinalQ = InOutPoseCtx.Pose[BoneIdx].GetRotation() * WeightedDelta;
		FinalQ.Normalize();
		InOutPoseCtx.Pose[BoneIdx].SetRotation(FinalQ);
	}
}

void FMorphRigAnimInstanceProxy::ApplyAdditiveHitLayer(FPoseContext& InOutPoseCtx, FName AdditiveClip, float SampleTime, float Weight) const
{
	if (AdditiveClip == NAME_None || Weight <= 0.01f)
	{
		return;
	}

	// Compute clean local-space delta against frame 0 of the hit clip itself (which equals combat_ready_base(0) -> zero foot snap!)
	TMap<FName, float> DummyCurves;
	FPoseContext HitBase(InOutPoseCtx);
	FPoseContext HitCurr(InOutPoseCtx);
	SampleClipPoseAndCurves(AdditiveClip, 0.0f, false, HitBase, DummyCurves);
	SampleClipPoseAndCurves(AdditiveClip, SampleTime, false, HitCurr, DummyCurves);

	for (FCompactPoseBoneIndex BoneIdx : InOutPoseCtx.Pose.ForEachBoneIndex())
	{
		const bool bIsUpper = (UpperBodyMask.Num() == InOutPoseCtx.Pose.GetNumBones()) && UpperBodyMask[BoneIdx.GetInt()];
		const bool bIsPelvis = (BoneIdx == PelvisIdx);
		if (!bIsUpper && !bIsPelvis)
		{
			continue; // Never displace thighs/calves/feet -> planted feet never snap!
		}

		const float BoneW = bIsPelvis ? (Weight * 0.35f) : Weight;
		const FQuat BaseQ = HitBase.Pose[BoneIdx].GetRotation();
		const FQuat CurrQ = HitCurr.Pose[BoneIdx].GetRotation();
		FQuat DeltaQ = BaseQ.Inverse() * CurrQ;
		DeltaQ.EnforceShortestArcWith(FQuat::Identity);
		FQuat NewQ = InOutPoseCtx.Pose[BoneIdx].GetRotation() * FQuat::Slerp(FQuat::Identity, DeltaQ, BoneW);
		NewQ.Normalize();
		InOutPoseCtx.Pose[BoneIdx].SetRotation(NewQ);

		if (bIsPelvis)
		{
			const FVector DeltaLoc = (HitCurr.Pose[BoneIdx].GetTranslation() - HitBase.Pose[BoneIdx].GetTranslation()) * BoneW;
			InOutPoseCtx.Pose[BoneIdx].AddToTranslation(DeltaLoc);
		}
	}
}

void FMorphRigAnimInstanceProxy::ApplyLookAtAndGroundIKAndSprings(FPoseContext& InOutPoseCtx) const
{
	const bool bDoLookAt = bEnableLookAt && (PrimaryState == EMorphRigPrimaryState::Locomotion);
	const bool bDoIK = GroundIKWeight > 0.01f && PelvisIdx.IsValid() &&
		ThighLIdx.IsValid() && CalfLIdx.IsValid() && FootLIdx.IsValid() &&
		ThighRIdx.IsValid() && CalfRIdx.IsValid() && FootRIdx.IsValid();
	const bool bDoSprings = (!CableSpringRad.IsNearlyZero(1e-4f) || !StrapSpringRad.IsNearlyZero(1e-4f));
	const bool bUpperReloadActive = (PrimaryState == EMorphRigPrimaryState::Locomotion) && (UpperClip == TEXT("reload")) && (UpperWeight > 0.01f);
	const bool bLockCell = CellBoneIdx.IsValid() && EmitterBoneRIdx.IsValid() &&
		!(PrimaryState != EMorphRigPrimaryState::Locomotion && PrimaryClip == TEXT("reload")) && !bUpperReloadActive;
	const bool bLockBeacon = BeaconBoneIdx.IsValid() && PelvisIdx.IsValid() &&
		!(PrimaryState != EMorphRigPrimaryState::Locomotion && PrimaryClip == TEXT("deploy"));

	if (!bDoLookAt && !bDoIK && !bDoSprings && !(FaceManual.bEnableManualOverride) && !bLockCell && !bLockBeacon)
	{
		return;
	}

	FCSPose<FCompactPose> CSPose;
	CSPose.InitPose(InOutPoseCtx.Pose);

	// 1. Ground-Adaptation Pelvis + 2-Bone Analytical Leg IK (up to 20 deg slope, 20 cm step)
	if (bDoIK)
	{
		const FVector OrigFootL = CSPose.GetComponentSpaceTransform(FootLIdx).GetLocation();
		const FVector OrigFootR = CSPose.GetComponentSpaceTransform(FootRIdx).GetLocation();

		const FVector PelvisDeltaZ(0.0f, 0.0f, PelvisOffsetZ * GroundIKWeight);
		FTransform PelvisCS = CSPose.GetComponentSpaceTransform(PelvisIdx);
		PelvisCS.AddToTranslation(PelvisDeltaZ);
		CSPose.SetComponentSpaceTransform(PelvisIdx, PelvisCS);

		if (bUpperReloadActive && CellBoneIdx.IsValid())
		{
			FTransform CellCS = CSPose.GetComponentSpaceTransform(CellBoneIdx);
			CellCS.AddToTranslation(PelvisDeltaZ);
			CSPose.SetComponentSpaceTransform(CellBoneIdx, CellCS);
		}

		auto SolveLeg = [&](FCompactPoseBoneIndex ThighI, FCompactPoseBoneIndex CalfI, FCompactPoseBoneIndex FootI,
			const FVector& PrePelvisFootPos, float FootZOff, const FVector& SurfaceNormalCS)
		{
			FTransform ThighCS = CSPose.GetComponentSpaceTransform(ThighI);
			FTransform CalfCS = CSPose.GetComponentSpaceTransform(CalfI);
			FTransform FootCS = CSPose.GetComponentSpaceTransform(FootI);

			// Fade IK lock gently when swing foot is lifted high above ground
			const float SwingHeight = FMath::Max(0.0f, PrePelvisFootPos.Z - 11.0f);
			const float LockAlpha = GroundIKWeight * FMath::Clamp(1.0f - (SwingHeight / 18.0f), 0.30f, 1.0f);

			const FVector DesiredPos = FVector(
				PrePelvisFootPos.X,
				PrePelvisFootPos.Y,
				PrePelvisFootPos.Z + FootZOff * LockAlpha);

			SolveAnalyticalTwoBoneIK_CS(ThighCS, CalfCS, FootCS, DesiredPos, MeshForwardCS);

			// Align ankle subtly to slope normal (clamped <= 22 deg so ankle never inverts!)
			FVector SafeNorm = SurfaceNormalCS.GetSafeNormal();
			if (SafeNorm.Z < 0.92f)
			{
				SafeNorm.Z = 0.92f;
				SafeNorm.Normalize();
			}
			const FQuat SlopeQ = FQuat::FindBetweenNormals(FVector::UpVector, SafeNorm);
			FQuat NewFootRot = FQuat::Slerp(FQuat::Identity, SlopeQ, LockAlpha) * FootCS.GetRotation();
			NewFootRot.Normalize();
			FootCS.SetRotation(NewFootRot);

			CSPose.SetComponentSpaceTransform(ThighI, ThighCS);
			CSPose.SetComponentSpaceTransform(CalfI, CalfCS);
			CSPose.SetComponentSpaceTransform(FootI, FootCS);
		};

		SolveLeg(ThighLIdx, CalfLIdx, FootLIdx, OrigFootL, FootOffsetZ_L, FootNormalCS_L);
		SolveLeg(ThighRIdx, CalfRIdx, FootRIdx, OrigFootR, FootOffsetZ_R, FootNormalCS_R);
	}

	// 2. Smooth Head & Stereo Eye Look-At (Component Space)
	if ((bDoLookAt || FaceManual.bEnableManualOverride) && HeadIdx.IsValid())
	{
		FTransform HeadCS = CSPose.GetComponentSpaceTransform(HeadIdx);
		const FVector HeadPos = HeadCS.GetLocation();
		FVector ToTarget = (LookAtTargetCS - HeadPos);
		if (ToTarget.SizeSquared() > 400.0f && bDoLookAt)
		{
			ToTarget.Normalize();
			const float FwdDot = FVector::DotProduct(ToTarget, MeshForwardCS);
			const float LeftDot = FVector::DotProduct(ToTarget, MeshLeftCS);
			const float TargetYawRad = FMath::Clamp(FMath::Atan2(LeftDot, FwdDot), -0.55f, 0.55f);
			const float TargetPitchRad = FMath::Clamp(FMath::Asin(FMath::Clamp(ToTarget.Z, -1.0f, 1.0f)), -0.38f, 0.38f);
			const FQuat HeadLookDelta = FQuat(FVector::UpVector, -TargetYawRad * 0.35f) * FQuat(MeshLeftCS, -TargetPitchRad * 0.35f);
			FQuat NewHeadRot = HeadLookDelta * HeadCS.GetRotation();
			NewHeadRot.Normalize();
			HeadCS.SetRotation(NewHeadRot);
			CSPose.SetComponentSpaceTransform(HeadIdx, HeadCS);
		}

		// Stereo eyes (manual override or target tracking)
		auto AimEye = [&](FCompactPoseBoneIndex EyeIdx)
		{
			if (!EyeIdx.IsValid()) { return; }
			FTransform EyeCS = CSPose.GetComponentSpaceTransform(EyeIdx);
			float YawR = 0.0f, PitchR = 0.0f;
			if (FaceManual.bEnableManualOverride)
			{
				YawR = FMath::DegreesToRadians(FMath::Clamp(FaceManual.EyeYawDeg, -28.0f, 28.0f));
				PitchR = FMath::DegreesToRadians(FMath::Clamp(FaceManual.EyePitchDeg, -20.0f, 20.0f));
			}
			else if (bDoLookAt)
			{
				const FVector Dir = (LookAtTargetCS - EyeCS.GetLocation()).GetSafeNormal();
				const float FwdDot = FVector::DotProduct(Dir, MeshForwardCS);
				const float LeftDot = FVector::DotProduct(Dir, MeshLeftCS);
				YawR = FMath::Clamp(-FMath::Atan2(LeftDot, FwdDot) * 0.55f, -0.42f, 0.42f);
				PitchR = FMath::Clamp(FMath::Asin(FMath::Clamp(Dir.Z, -1.0f, 1.0f)) * 0.55f, -0.30f, 0.30f);
			}
			if (FMath::Abs(YawR) > 1e-3f || FMath::Abs(PitchR) > 1e-3f)
			{
				const FQuat EyeDelta = FQuat(FVector::UpVector, YawR) * FQuat(MeshLeftCS, -PitchR);
				FQuat NewEyeQ = EyeDelta * EyeCS.GetRotation();
				NewEyeQ.Normalize();
				EyeCS.SetRotation(NewEyeQ);
				CSPose.SetComponentSpaceTransform(EyeIdx, EyeCS);
			}
		};
		AimEye(EyeLIdx);
		AimEye(EyeRIdx);
	}

	// 3. Critically-Damped Secondary Settle on cable_01..03 and strap_01..03 (strictly clamped, zero runaway!)
	if (bDoSprings)
	{
		for (int32 i = 0; i < 3; ++i)
		{
			const float ChainScale = 0.45f + 0.25f * i;
			if (CableIdx[i].IsValid())
			{
				FTransform T = CSPose.GetComponentSpaceTransform(CableIdx[i]);
				const FQuat LagQ = FQuat(FVector(1, 0, 0), CableSpringRad.X * ChainScale) * FQuat(FVector(0, 1, 0), CableSpringRad.Y * ChainScale);
				FQuat NewQ = LagQ * T.GetRotation();
				NewQ.Normalize();
				T.SetRotation(NewQ);
				CSPose.SetComponentSpaceTransform(CableIdx[i], T);
			}
			if (StrapIdx[i].IsValid())
			{
				FTransform T = CSPose.GetComponentSpaceTransform(StrapIdx[i]);
				const FQuat LagQ = FQuat(FVector(1, 0, 0), StrapSpringRad.X * ChainScale) * FQuat(FVector(0, 1, 0), StrapSpringRad.Y * ChainScale);
				FQuat NewQ = LagQ * T.GetRotation();
				NewQ.Normalize();
				T.SetRotation(NewQ);
				CSPose.SetComponentSpaceTransform(StrapIdx[i], T);
			}
		}
	}

	// 4. Keep root-parented detachable props rigidly docked whenever reload/deploy handoffs are not active
	if (bLockCell)
	{
		const FTransform EmitterCS = CSPose.GetComponentSpaceTransform(EmitterBoneRIdx);
		CSPose.SetComponentSpaceTransform(CellBoneIdx, RefCellInEmitter * EmitterCS);
	}
	if (bLockBeacon)
	{
		const FTransform PelvisCSCurr = CSPose.GetComponentSpaceTransform(PelvisIdx);
		CSPose.SetComponentSpaceTransform(BeaconBoneIdx, RefBeaconInPelvis * PelvisCSCurr);
	}

	FCSPose<FCompactPose>::ConvertComponentPosesToLocalPosesSafe(CSPose, InOutPoseCtx.Pose);
}

bool FMorphRigAnimInstanceProxy::Evaluate(FPoseContext& Output)
{
	Output.ResetToRefPose();
	const int32 NumBones = Output.Pose.GetNumBones();
	if (NumBones <= 0)
	{
		return true;
	}
	if (!RootIdx.IsValid() || UpperBodyMask.Num() != NumBones)
	{
		const_cast<FMorphRigAnimInstanceProxy*>(this)->CacheBones();
	}

	// Stasis holds the exact frozen pose & facial curves while active
	if (bStasis && bHasStasisPose && StasisPose.Num() == NumBones)
	{
		for (int32 i = 0; i < NumBones; ++i)
		{
			Output.Pose[FCompactPoseBoneIndex(i)] = StasisPose[i];
		}
		for (const auto& KV : StasisCurves)
		{
			Output.Curve.Set(KV.Key, KV.Value);
			Output.Curve.SetFlags(KV.Key, UE::Anim::ECurveElementFlags::MorphTarget);
		}
		return true;
	}
	bHasStasisPose = false;

	// Capture pose snapshot from last frame's evaluated output when an arbitrary-point interrupt/transition begins
	if (bCaptureSnapshotThisFrame && LastEvaluatedPose.Num() == NumBones)
	{
		SnapshotPose = LastEvaluatedPose;
		SnapshotCurves = LastEvaluatedCurves;
	}

	TMap<FName, float> EvaluatedCurves;

	// 1. Evaluate Base Layer (Locomotion vs Full-Body State / Direct Browser Clip)
	if (PrimaryState == EMorphRigPrimaryState::Locomotion)
	{
		EvaluateLocomotionPose(Output, EvaluatedCurves);

		// 2. Upper-Body Layered Branch (moving ranged_fire, ranged_burst, reload, cast_directional)
		if (UpperClip != NAME_None && UpperWeight > 0.01f && UpperBodyMask.Num() == NumBones)
		{
			FPoseContext UpperCtx(Output);
			TMap<FName, float> UpperCurves;
			SampleClipPoseAndCurves(UpperClip, UpperTime, false, UpperCtx, UpperCurves);

			for (FCompactPoseBoneIndex BoneIdx : Output.Pose.ForEachBoneIndex())
			{
				if (!UpperBodyMask[BoneIdx.GetInt()])
				{
					continue;
				}
				FTransform& A = Output.Pose[BoneIdx];
				const FTransform& B = UpperCtx.Pose[BoneIdx];
				FQuat QA = A.GetRotation();
				FQuat QB = B.GetRotation();
				QB.EnforceShortestArcWith(QA);
				FQuat QOut = FQuat::Slerp(QA, QB, UpperWeight);
				QOut.Normalize();
				A.SetRotation(QOut);
				A.SetTranslation(FMath::Lerp(A.GetTranslation(), B.GetTranslation(), UpperWeight));
			}
			if (UpperClip == TEXT("reload") && CellBoneIdx.IsValid() && Spine03Idx.IsValid() && EmitterBoneRIdx.IsValid())
			{
				FCSPose<FCompactPose> UpperCS;
				UpperCS.InitPose(UpperCtx.Pose);
				const FTransform CellRelSpine = UpperCS.GetComponentSpaceTransform(CellBoneIdx).GetRelativeTransform(UpperCS.GetComponentSpaceTransform(Spine03Idx));

				FCSPose<FCompactPose> OutCS;
				OutCS.InitPose(Output.Pose);
				const FTransform DockedCS = RefCellInEmitter * OutCS.GetComponentSpaceTransform(EmitterBoneRIdx);
				const FTransform ReloadCS = CellRelSpine * OutCS.GetComponentSpaceTransform(Spine03Idx);
				FTransform BlendedCellCS;
				BlendedCellCS.Blend(DockedCS, ReloadCS, UpperWeight);
				OutCS.SetComponentSpaceTransform(CellBoneIdx, BlendedCellCS);
				FCSPose<FCompactPose>::ConvertComponentPosesToLocalPosesSafe(OutCS, Output.Pose);
			}
			BlendCurvesInPlace(EvaluatedCurves, UpperCurves, UpperWeight);
		}

		// 3. Calibrated 9-Sample Aim Grid Layer (-60..+60 Yaw, -35..+35 Pitch)
		if (bEnableAim)
		{
			ApplyAimGridLayer(Output, AimYawDeg, AimPitchDeg, AimWeight);
		}
	}
	else
	{
		SampleClipPoseAndCurves(PrimaryClip, PrimaryTime, bPrimaryLoop, Output, EvaluatedCurves, bZeroRootXY);
	}

	// 4. Local-Space Additive Hit Reaction Layer (layers over idle and motion without snapping planted feet)
	if (HitClip != NAME_None && HitWeight > 0.01f && PrimaryState != EMorphRigPrimaryState::DeadHeld && PrimaryState != EMorphRigPrimaryState::DeathDying)
	{
		ApplyAdditiveHitLayer(Output, HitClip, HitTime, HitWeight);
		EvaluatedCurves.Add(TEXT("expr_pain"), FMath::Max(EvaluatedCurves.FindRef(TEXT("expr_pain")), HitWeight * 0.85f));
	}

	// 5. Ground-Adaptation IK, Look-At, and Damped Secondary Springs
	ApplyLookAtAndGroundIKAndSprings(Output);

	// 6. Pose-Snapshot Crossfade (guarantees smooth blend from arbitrary interruption point without snapping to frame 0!)
	if (SnapshotAlpha > 0.01f && SnapshotPose.Num() == NumBones)
	{
		for (int32 i = 0; i < NumBones; ++i)
		{
			const FCompactPoseBoneIndex Idx(i);
			const FTransform& SnapT = SnapshotPose[i];
			FTransform& CurrT = Output.Pose[Idx];
			FQuat QS = SnapT.GetRotation();
			FQuat QC = CurrT.GetRotation();
			QS.EnforceShortestArcWith(QC);
			FQuat QBlend = FQuat::Slerp(QC, QS, SnapshotAlpha);
			QBlend.Normalize();
			CurrT.SetRotation(QBlend);
			CurrT.SetTranslation(FMath::Lerp(CurrT.GetTranslation(), SnapT.GetTranslation(), SnapshotAlpha));
			CurrT.SetScale3D(FMath::Lerp(CurrT.GetScale3D(), SnapT.GetScale3D(), SnapshotAlpha));
		}
		BlendCurvesInPlace(EvaluatedCurves, SnapshotCurves, SnapshotAlpha);
	}

	// 7. Soft CC Facial Overlays & Live Interactive Facial/Viseme Control Panel Overrides
	if (bFear)
	{
		EvaluatedCurves.Add(TEXT("expr_concern_sadness"), 0.75f);
		EvaluatedCurves.Add(TEXT("expr_surprise"), 0.45f);
	}
	else if (bCharm)
	{
		EvaluatedCurves.Add(TEXT("expr_joy_confidence"), 0.85f);
	}
	else if (bTaunt)
	{
		EvaluatedCurves.Add(TEXT("expr_anger"), 0.88f);
	}

	if (FaceManual.bEnableManualOverride)
	{
		auto SetManual = [&EvaluatedCurves](const TCHAR* Name, float Val)
		{
			if (Val > 0.001f) { EvaluatedCurves.Add(FName(Name), Val); }
			else { EvaluatedCurves.Remove(FName(Name)); }
		};
		SetManual(TEXT("blink_l"), FaceManual.BlinkL);
		SetManual(TEXT("blink_r"), FaceManual.BlinkR);
		SetManual(TEXT("squint_l"), FaceManual.SquintL);
		SetManual(TEXT("squint_r"), FaceManual.SquintR);
		SetManual(TEXT("brow_up_l"), FaceManual.BrowUpL);
		SetManual(TEXT("brow_up_r"), FaceManual.BrowUpR);
		SetManual(TEXT("brow_down_l"), FaceManual.BrowDownL);
		SetManual(TEXT("brow_down_r"), FaceManual.BrowDownR);
		SetManual(TEXT("cheek_raise_l"), FaceManual.CheekRaiseL);
		SetManual(TEXT("cheek_raise_r"), FaceManual.CheekRaiseR);
		SetManual(TEXT("smile_l"), FaceManual.SmileL);
		SetManual(TEXT("smile_r"), FaceManual.SmileR);
		SetManual(TEXT("frown_l"), FaceManual.FrownL);
		SetManual(TEXT("frown_r"), FaceManual.FrownR);
		SetManual(TEXT("jaw_open"), FaceManual.JawOpen);
		SetManual(TEXT("lip_close"), FaceManual.LipClose);
		SetManual(TEXT("mouth_wide"), FaceManual.MouthWide);
		SetManual(TEXT("mouth_pucker"), FaceManual.MouthPucker);
		SetManual(TEXT("mouth_funnel"), FaceManual.MouthFunnel);
		SetManual(TEXT("tongue_up"), FaceManual.TongueUp);
		SetManual(TEXT("tongue_out"), FaceManual.TongueOut);
		if (FaceManual.ActiveViseme != NAME_None && FaceManual.ActiveVisemeWeight > 0.001f)
		{
			EvaluatedCurves.Add(FaceManual.ActiveViseme, FaceManual.ActiveVisemeWeight);
		}
		if (FaceManual.ActivePreset != NAME_None && FaceManual.ActivePresetWeight > 0.001f)
		{
			EvaluatedCurves.Add(FaceManual.ActivePreset, FaceManual.ActivePresetWeight);
		}
	}

	for (const auto& KV : EvaluatedCurves)
	{
		Output.Curve.Set(KV.Key, KV.Value);
		Output.Curve.SetFlags(KV.Key, UE::Anim::ECurveElementFlags::MorphTarget);
	}

	// Cache final output pose for seamless pose-snapshot crossfade or Stasis freeze on next frame
	LastEvaluatedPose.SetNumUninitialized(NumBones);
	for (int32 i = 0; i < NumBones; ++i)
	{
		LastEvaluatedPose[i] = Output.Pose[FCompactPoseBoneIndex(i)];
	}
	LastEvaluatedCurves = EvaluatedCurves;
	if (bStasis && !bHasStasisPose)
	{
		StasisPose = LastEvaluatedPose;
		StasisCurves = LastEvaluatedCurves;
		bHasStasisPose = true;
	}

	return true;
}

void FMorphRigAnimInstanceProxy::PostEvaluate(UAnimInstance* InAnimInstance)
{
	FAnimInstanceProxy::PostEvaluate(InAnimInstance);
	if (!InAnimInstance)
	{
		return;
	}
	if (USkeletalMeshComponent* SkelComp = InAnimInstance->GetSkelMeshComponent())
	{
		const TMap<FName, float>& ActiveCurves = (bStasis && bHasStasisPose) ? StasisCurves : LastEvaluatedCurves;
		const bool bHasCurves = (ActiveCurves.Num() > 0);
		if (bHasCurves || bPrevHadMorphCurves)
		{
			SkelComp->ApplyAnimationCurvesToComponent(nullptr, &ActiveCurves);
			bPrevHadMorphCurves = bHasCurves;
		}
	}
}

// ============================================================================
// UMorphRigAnimInstance
// ============================================================================

UMorphRigAnimInstance::UMorphRigAnimInstance()
{
}

FAnimInstanceProxy* UMorphRigAnimInstance::CreateAnimInstanceProxy()
{
	AnimProxy = FMorphRigAnimInstanceProxy(this);
	return &AnimProxy;
}

void UMorphRigAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy)
{
}

void UMorphRigAnimInstance::NativeInitializeAnimation()
{
	Super::NativeInitializeAnimation();

	LoadedSequences.Reset();
	for (int32 i = 0; i < GMorphRigClipCount; ++i)
	{
		const FName ClipName(GMorphRigClips[i].ClipId);
		if (UAnimSequence* Seq = LoadObject<UAnimSequence>(nullptr, GMorphRigClips[i].AssetObjectPath))
		{
			LoadedSequences.Add(ClipName, Seq);
		}
	}

	PrimaryState = EMorphRigPrimaryState::Locomotion;
	PrimaryClip = TEXT("idle_combat");
	PrimaryDuration = GetClipDuration(PrimaryClip);
	bPrimaryLoop = true;
}

int32 UMorphRigAnimInstance::GetStatePriority(EMorphRigPrimaryState State)
{
	switch (State)
	{
	case EMorphRigPrimaryState::DeathDying:
	case EMorphRigPrimaryState::DeadHeld:
	case EMorphRigPrimaryState::Respawning:
		return 50; // Terminal / Respawn (Highest)
	case EMorphRigPrimaryState::DisableStunStart:
	case EMorphRigPrimaryState::DisableStunLoop:
	case EMorphRigPrimaryState::DisableStunEnd:
	case EMorphRigPrimaryState::DisableSleepStart:
	case EMorphRigPrimaryState::DisableSleepLoop:
	case EMorphRigPrimaryState::DisableSleepEnd:
	case EMorphRigPrimaryState::DisableKnockback:
	case EMorphRigPrimaryState::DisableKnockupStart:
	case EMorphRigPrimaryState::DisableKnockupAir:
	case EMorphRigPrimaryState::DisableKnockdown:
	case EMorphRigPrimaryState::DisableProne:
	case EMorphRigPrimaryState::DisableGetup:
		return 40; // Hard Disables
	case EMorphRigPrimaryState::MobilityDash:
	case EMorphRigPrimaryState::MobilityBlink:
		return 30; // Mobility Override
	case EMorphRigPrimaryState::AbilityOneShot:
	case EMorphRigPrimaryState::ChannelStart:
	case EMorphRigPrimaryState::ChannelLoop:
	case EMorphRigPrimaryState::ChannelEnd:
	case EMorphRigPrimaryState::ChannelInterrupt:
	case EMorphRigPrimaryState::ChargeStart:
	case EMorphRigPrimaryState::ChargeHold:
	case EMorphRigPrimaryState::ChargeRelease:
	case EMorphRigPrimaryState::ChargeCancel:
	case EMorphRigPrimaryState::UplinkStart:
	case EMorphRigPrimaryState::UplinkLoop:
	case EMorphRigPrimaryState::UplinkEnd:
	case EMorphRigPrimaryState::UplinkCancel:
		return 20; // Full-body Abilities & Sustained Actions
	case EMorphRigPrimaryState::DirectClipInspect:
		return 15;
	case EMorphRigPrimaryState::Locomotion:
	default:
		return 10;
	}
}

float UMorphRigAnimInstance::GetClipDuration(FName ClipId) const
{
	if (const TObjectPtr<UAnimSequence>* Found = LoadedSequences.Find(ClipId))
	{
		if (*Found)
		{
			return FMath::Max(0.0333f, (*Found)->GetPlayLength());
		}
	}
	for (int32 i = 0; i < GMorphRigClipCount; ++i)
	{
		if (ClipId == GMorphRigClips[i].ClipId)
		{
			return FMath::Max(0.0333f, GMorphRigClips[i].DurationSec);
		}
	}
	return 1.0f;
}

bool UMorphRigAnimInstance::IsClipLooping(FName ClipId) const
{
	for (int32 i = 0; i < GMorphRigClipCount; ++i)
	{
		if (ClipId == GMorphRigClips[i].ClipId)
		{
			return FCString::Strcmp(GMorphRigClips[i].Form, TEXT("loop")) == 0;
		}
	}
	return false;
}

bool UMorphRigAnimInstance::AllowsLocomotionInput() const
{
	if (bStasis || bRooted)
	{
		return false;
	}
	return PrimaryState == EMorphRigPrimaryState::Locomotion;
}

FString UMorphRigAnimInstance::GetReadableStateSummary() const
{
	const UEnum* EnumPtr = StaticEnum<EMorphRigPrimaryState>();
	const FString StateStr = EnumPtr ? EnumPtr->GetNameStringByValue(static_cast<int64>(PrimaryState)) : TEXT("State");
	FString Summary = FString::Printf(TEXT("%s | Clip: %s (%.2fs / %.2fs) | Rate: %.2fx"),
		*StateStr, *PrimaryClip.ToString(), PrimaryTime, PrimaryDuration, ActionPlayRate);
	if (UpperClip != NAME_None && UpperWeight > 0.05f)
	{
		Summary += FString::Printf(TEXT(" + Upper[%s]"), *UpperClip.ToString());
	}
	if (HitClip != NAME_None && HitWeight > 0.05f)
	{
		Summary += FString::Printf(TEXT(" + Hit[%s]"), *HitClip.ToString());
	}
	if (LocoSubClip != NAME_None && LocoSubWeight > 0.05f && PrimaryState == EMorphRigPrimaryState::Locomotion)
	{
		Summary += FString::Printf(TEXT(" + Sub[%s]"), *LocoSubClip.ToString());
	}
	return Summary;
}

void UMorphRigAnimInstance::RequestSnapshotCrossfade(float BlendDuration)
{
	bPendingSnapshotCapture = true;
	SnapshotCrossfadeDuration = FMath::Max(0.01f, BlendDuration);
	SnapshotCrossfadeElapsed = 0.0f;
}

void UMorphRigAnimInstance::SetPrimaryClipInternal(EMorphRigPrimaryState NewState, FName NewClip, bool bLoop, float CrossfadeSec)
{
	if (CrossfadeSec > 0.001f)
	{
		RequestSnapshotCrossfade(CrossfadeSec);
	}
	PrimaryState = NewState;
	PrimaryClip = NewClip;
	PrimaryTime = 0.0f;
	PrimaryDuration = GetClipDuration(NewClip);
	bPrimaryLoop = bLoop;
	PrimaryInstanceCounter++;
	FiredPrimaryMask = 0;
	PrimaryLoopIndex = 0;

	// Clear lower-priority upper-body layer when entering full-body override
	if (NewState != EMorphRigPrimaryState::Locomotion)
	{
		UpperBodyMode = EMorphRigUpperBodyMode::None;
		UpperClip = NAME_None;
		UpperWeight = 0.0f;
		LocoSubClip = NAME_None;
		LocoSubWeight = 0.0f;
	}
}

void UMorphRigAnimInstance::ResetToReadyState()
{
	bWounded = false;
	bRooted = false;
	bSilenced = false;
	bDisarmed = false;
	bFeared = false;
	bCharmed = false;
	bTaunted = false;
	bStasis = false;
	ActionPlayRate = 1.0f;
	MeleeComboIndex = 0;
	bMeleeQueuedNext = false;
	HitClip = NAME_None;
	HitWeight = 0.0f;
	FaceManual.Reset();
	SetPrimaryClipInternal(EMorphRigPrimaryState::Locomotion, TEXT("idle_combat"), true, 0.14f);
}

void UMorphRigAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeUpdateAnimation(DeltaSeconds);

	const float SafeDt = FMath::Clamp(DeltaSeconds, 0.0f, 0.1f);
	ActionPlayRate = FMath::Clamp(ActionPlayRate, 0.5f, 1.5f);
	const float EffectiveDt = bStasis ? 0.0f : (SafeDt * ActionPlayRate);

	if (SnapshotCrossfadeElapsed < SnapshotCrossfadeDuration)
	{
		SnapshotCrossfadeElapsed += SafeDt;
	}

	// Update Ground IK traces & damped secondary springs
	UpdateGroundIKAndSprings(SafeDt);

	if (bStasis)
	{
		return;
	}

	// 1. Update Additive Hit Reaction Layer
	if (HitClip != NAME_None)
	{
		const float HitDur = GetClipDuration(HitClip);
		HitTime += EffectiveDt;
		if (HitTime >= HitDur)
		{
			HitClip = NAME_None;
			HitWeight = 0.0f;
		}
		else
		{
			const float U = HitTime / FMath::Max(0.05f, HitDur);
			HitWeight = FMath::Sin(U * PI);
		}
	}

	// 2. Update Locomotion State (when active)
	if (PrimaryState == EMorphRigPrimaryState::Locomotion)
	{
		const FName DesiredIdle = bWounded ? FName(TEXT("idle_wounded")) : (bCombatStance ? FName(TEXT("idle_combat")) : FName(TEXT("idle_relaxed")));
		if (PrimaryClip != DesiredIdle && GroundSpeed < 5.0f)
		{
			PrimaryClip = DesiredIdle;
			PrimaryDuration = GetClipDuration(PrimaryClip);
		}
		const float PrevPrimaryT = PrimaryTime;
		PrimaryTime += EffectiveDt;
		CheckAndFireMarkers(PrimaryClip, PrevPrimaryT, PrimaryTime, true, TEXT("Locomotion"), FiredPrimaryMask, PrimaryLoopIndex);

		// Advance continuous gait phase & fire deduplicated foot contact markers once per half-cycle
		if (GroundSpeed > 5.0f && bIsGrounded)
		{
			const float RefCycleFreq = (GroundSpeed <= 150.0f) ? FMath::Lerp(0.8f, 1.08f, GroundSpeed / 150.0f)
				: ((GroundSpeed <= 400.0f) ? FMath::Lerp(1.08f, 1.48f, (GroundSpeed - 150.0f) / 250.0f) : 1.72f);
			const float PrevPhase = GaitPhase;
			GaitPhase = FMath::Fmod(GaitPhase + EffectiveDt * RefCycleFreq, 1.0f);

			const int32 HalfIdx = (GaitPhase < 0.5f) ? 0 : 1;
			if (HalfIdx != GaitHalfCycleIndex)
			{
				GaitHalfCycleIndex = HalfIdx;
				const FName ActiveGaitName = (GroundSpeed > 450.0f) ? TEXT("sprint_f") : ((GroundSpeed > 180.0f) ? TEXT("run_f") : TEXT("walk_f"));
				EmitMarkerEvent(ActiveGaitName, (HalfIdx == 0) ? TEXT("foot_l_contact") : TEXT("foot_r_contact"), TEXT("Locomotion"), GaitPhase);
			}
			(void)PrevPhase;
		}
		else
		{
			GaitHalfCycleIndex = -1;
		}

		// Aerial state transitions (jump_start -> jump_air -> fall -> jump_land / land_heavy)
		if (!bIsGrounded)
		{
			AirborneTime += SafeDt;
			if (LocoSubClip == TEXT("jump_start"))
			{
				LocoSubTime += EffectiveDt;
				LocoSubWeight = 1.0f;
				int32 DummyLoop = 0;
				CheckAndFireMarkers(LocoSubClip, LocoSubTime - EffectiveDt, LocoSubTime, false, TEXT("LocomotionSub"), FiredLocoSubMask, DummyLoop);
				if (LocoSubTime >= GetClipDuration(TEXT("jump_start")))
				{
					LocoSubClip = TEXT("jump_air");
					LocoSubTime = 0.0f;
					bLocoSubLoop = true;
					FiredLocoSubMask = 0;
				}
			}
			else if (AirborneTime > 0.65f && LocoSubClip != TEXT("fall"))
			{
				RequestSnapshotCrossfade(0.18f);
				LocoSubClip = TEXT("fall");
				LocoSubTime = 0.0f;
				LocoSubWeight = 1.0f;
				bLocoSubLoop = true;
			}
			else if (LocoSubClip == NAME_None)
			{
				LocoSubClip = TEXT("jump_air");
				LocoSubTime = 0.0f;
				LocoSubWeight = 1.0f;
				bLocoSubLoop = true;
			}
			else
			{
				LocoSubTime += EffectiveDt;
				LocoSubWeight = 1.0f;
			}
		}
		else
		{
			if (AirborneTime > 0.05f)
			{
				// Just touched ground! Choose land_heavy vs jump_land
				const FName LandClip = (AirborneTime > 0.65f) ? FName(TEXT("land_heavy")) : FName(TEXT("jump_land"));
				RequestSnapshotCrossfade(0.10f);
				LocoSubClip = LandClip;
				LocoSubTime = 0.0f;
				LocoSubWeight = 1.0f;
				bLocoSubLoop = false;
				FiredLocoSubMask = 0;
				AirborneTime = 0.0f;
			}
			else if (LocoSubClip != NAME_None)
			{
				const float SubDur = GetClipDuration(LocoSubClip);
				const float PrevSubT = LocoSubTime;
				LocoSubTime += EffectiveDt;
				int32 DummyLoop = 0;
				CheckAndFireMarkers(LocoSubClip, PrevSubT, LocoSubTime, false, TEXT("LocomotionSub"), FiredLocoSubMask, DummyLoop);
				if (LocoSubTime >= SubDur)
				{
					LocoSubClip = NAME_None;
					LocoSubWeight = 0.0f;
				}
				else
				{
					const float FadeOut = FMath::Clamp((SubDur - LocoSubTime) / 0.14f, 0.0f, 1.0f);
					LocoSubWeight = FadeOut;
				}
			}
		}

		// Update Upper-Body Layered Action
		if (UpperClip != NAME_None)
		{
			const float UpDur = GetClipDuration(UpperClip);
			const float PrevUpT = UpperTime;
			UpperTime += EffectiveDt;
			int32 DummyLoop = 0;
			CheckAndFireMarkers(UpperClip, PrevUpT, UpperTime, false, TEXT("UpperBody"), FiredUpperMask, DummyLoop);
			if (UpperTime >= UpDur)
			{
				UpperBodyMode = EMorphRigUpperBodyMode::None;
				UpperClip = NAME_None;
				UpperWeight = 0.0f;
			}
			else
			{
				const float BlendIn = FMath::Clamp(UpperTime / 0.08f, 0.0f, 1.0f);
				const float BlendOut = FMath::Clamp((UpDur - UpperTime) / 0.12f, 0.0f, 1.0f);
				UpperWeight = FMath::Min(BlendIn, BlendOut);
			}
		}
		return;
	}

	// 3. Update Full-Body Primary States (Dash, Blink, Melee, Channel, Charge, Uplink, Disables, Death, Respawn, Browser)
	const float PrevT = PrimaryTime;
	PrimaryTime += EffectiveDt;
	CheckAndFireMarkers(PrimaryClip, PrevT, PrimaryTime, bPrimaryLoop, TEXT("FullBody"), FiredPrimaryMask, PrimaryLoopIndex);

	switch (PrimaryState)
	{
	case EMorphRigPrimaryState::DirectClipInspect:
		if (!bPrimaryLoop && PrimaryTime >= PrimaryDuration)
		{
			PrimaryTime = PrimaryDuration; // Hold final frame in inspector until replayed or exited
		}
		break;

	case EMorphRigPrimaryState::MobilityDash:
		if (PrimaryTime >= PrimaryDuration)
		{
			SetPrimaryClipInternal(EMorphRigPrimaryState::Locomotion, TEXT("idle_combat"), true, 0.12f);
		}
		break;

	case EMorphRigPrimaryState::MobilityBlink:
		if (PrimaryClip == TEXT("blink_out") && PrimaryTime >= PrimaryDuration)
		{
			SetPrimaryClipInternal(EMorphRigPrimaryState::MobilityBlink, TEXT("blink_in"), false, 0.04f);
		}
		else if (PrimaryClip == TEXT("blink_in") && PrimaryTime >= PrimaryDuration)
		{
			SetPrimaryClipInternal(EMorphRigPrimaryState::Locomotion, TEXT("idle_combat"), true, 0.12f);
		}
		break;

	case EMorphRigPrimaryState::AbilityOneShot:
		// Check Melee 1 -> 2 -> 3 combo chain window
		if (bMeleeQueuedNext && PrimaryTime >= PrimaryDuration * 0.58f)
		{
			bMeleeQueuedNext = false;
			if (MeleeComboIndex == 1)
			{
				MeleeComboIndex = 2;
				SetPrimaryClipInternal(EMorphRigPrimaryState::AbilityOneShot, TEXT("melee_2"), false, 0.12f);
				break;
			}
			if (MeleeComboIndex == 2)
			{
				MeleeComboIndex = 3;
				SetPrimaryClipInternal(EMorphRigPrimaryState::AbilityOneShot, TEXT("melee_3"), false, 0.12f);
				break;
			}
		}
		if (PrimaryTime >= PrimaryDuration)
		{
			MeleeComboIndex = 0;
			bMeleeQueuedNext = false;
			SetPrimaryClipInternal(EMorphRigPrimaryState::Locomotion, TEXT("idle_combat"), true, 0.16f);
		}
		break;

	// --- CHANNEL ---
	case EMorphRigPrimaryState::ChannelStart:
		if (PrimaryTime >= PrimaryDuration)
		{
			SustainedHoldTimer = 0.0f;
			SetPrimaryClipInternal(EMorphRigPrimaryState::ChannelLoop, TEXT("channel_loop"), true, 0.10f);
		}
		break;
	case EMorphRigPrimaryState::ChannelLoop:
		SustainedHoldTimer += EffectiveDt;
		if (SustainedAutoFinishTime > 0.0f && SustainedHoldTimer >= SustainedAutoFinishTime)
		{
			FinishChannel();
		}
		break;
	case EMorphRigPrimaryState::ChannelEnd:
	case EMorphRigPrimaryState::ChannelInterrupt:
		if (PrimaryTime >= PrimaryDuration)
		{
			SetPrimaryClipInternal(EMorphRigPrimaryState::Locomotion, TEXT("idle_combat"), true, 0.14f);
		}
		break;

	// --- CHARGE ---
	case EMorphRigPrimaryState::ChargeStart:
		if (PrimaryTime >= PrimaryDuration)
		{
			SustainedHoldTimer = 0.0f;
			SetPrimaryClipInternal(EMorphRigPrimaryState::ChargeHold, TEXT("charge_hold"), true, 0.10f);
		}
		break;
	case EMorphRigPrimaryState::ChargeHold:
		SustainedHoldTimer += EffectiveDt;
		break;
	case EMorphRigPrimaryState::ChargeRelease:
	case EMorphRigPrimaryState::ChargeCancel:
		if (PrimaryTime >= PrimaryDuration)
		{
			SetPrimaryClipInternal(EMorphRigPrimaryState::Locomotion, TEXT("idle_combat"), true, 0.14f);
		}
		break;

	// --- UPLINK ---
	case EMorphRigPrimaryState::UplinkStart:
		if (PrimaryTime >= PrimaryDuration)
		{
			SustainedHoldTimer = 0.0f;
			SetPrimaryClipInternal(EMorphRigPrimaryState::UplinkLoop, TEXT("uplink_loop"), true, 0.10f);
		}
		break;
	case EMorphRigPrimaryState::UplinkLoop:
		SustainedHoldTimer += EffectiveDt;
		if (SustainedAutoFinishTime > 0.0f && SustainedHoldTimer >= SustainedAutoFinishTime)
		{
			FinishUplink();
		}
		break;
	case EMorphRigPrimaryState::UplinkEnd:
	case EMorphRigPrimaryState::UplinkCancel:
		if (PrimaryTime >= PrimaryDuration)
		{
			SetPrimaryClipInternal(EMorphRigPrimaryState::Locomotion, TEXT("idle_combat"), true, 0.14f);
		}
		break;

	// --- HARD DISABLES: STUN, SLEEP, KNOCKBACK, KNOCKUP -> KNOCKDOWN -> PRONE -> GETUP ---
	case EMorphRigPrimaryState::DisableStunStart:
		if (PrimaryTime >= PrimaryDuration)
		{
			SustainedHoldTimer = 0.0f;
			SetPrimaryClipInternal(EMorphRigPrimaryState::DisableStunLoop, TEXT("stun_loop"), true, 0.10f);
		}
		break;
	case EMorphRigPrimaryState::DisableStunLoop:
		SustainedHoldTimer += EffectiveDt;
		if (SustainedAutoFinishTime > 0.0f && SustainedHoldTimer >= SustainedAutoFinishTime)
		{
			SetPrimaryClipInternal(EMorphRigPrimaryState::DisableStunEnd, TEXT("stun_end"), false, 0.12f);
		}
		break;
	case EMorphRigPrimaryState::DisableStunEnd:
		if (PrimaryTime >= PrimaryDuration)
		{
			SetPrimaryClipInternal(EMorphRigPrimaryState::Locomotion, TEXT("idle_combat"), true, 0.14f);
		}
		break;

	case EMorphRigPrimaryState::DisableSleepStart:
		if (PrimaryTime >= PrimaryDuration)
		{
			SustainedHoldTimer = 0.0f;
			SetPrimaryClipInternal(EMorphRigPrimaryState::DisableSleepLoop, TEXT("sleep_loop"), true, 0.12f);
		}
		break;
	case EMorphRigPrimaryState::DisableSleepLoop:
		SustainedHoldTimer += EffectiveDt;
		if (SustainedAutoFinishTime > 0.0f && SustainedHoldTimer >= SustainedAutoFinishTime)
		{
			WakeFromSleep();
		}
		break;
	case EMorphRigPrimaryState::DisableSleepEnd:
	case EMorphRigPrimaryState::DisableKnockback:
		if (PrimaryTime >= PrimaryDuration)
		{
			SetPrimaryClipInternal(EMorphRigPrimaryState::Locomotion, TEXT("idle_combat"), true, 0.14f);
		}
		break;

	case EMorphRigPrimaryState::DisableKnockupStart:
		if (PrimaryTime >= PrimaryDuration)
		{
			SustainedHoldTimer = 0.0f;
			SetPrimaryClipInternal(EMorphRigPrimaryState::DisableKnockupAir, TEXT("knockup_air"), true, 0.10f);
		}
		break;
	case EMorphRigPrimaryState::DisableKnockupAir:
		SustainedHoldTimer += EffectiveDt;
		if (bIsGrounded && SustainedHoldTimer > 0.25f)
		{
			TriggerKnockdown(bKnockdownIsFront, 1.0f);
		}
		break;
	case EMorphRigPrimaryState::DisableKnockdown:
		if (PrimaryTime >= PrimaryDuration)
		{
			SustainedHoldTimer = 0.0f;
			SetPrimaryClipInternal(
				EMorphRigPrimaryState::DisableProne,
				bKnockdownIsFront ? TEXT("prone_front") : TEXT("prone_back"),
				true,
				0.06f);
		}
		break;
	case EMorphRigPrimaryState::DisableProne:
		SustainedHoldTimer += EffectiveDt;
		if (SustainedAutoFinishTime > 0.0f && SustainedHoldTimer >= SustainedAutoFinishTime)
		{
			TriggerGetup();
		}
		break;
	case EMorphRigPrimaryState::DisableGetup:
		if (PrimaryTime >= PrimaryDuration)
		{
			SetPrimaryClipInternal(EMorphRigPrimaryState::Locomotion, TEXT("idle_combat"), true, 0.14f);
		}
		break;

	// --- TERMINAL DEATH -> EXACT CONNECTED DEAD POSE -> RESPAWN ---
	case EMorphRigPrimaryState::DeathDying:
		if (PrimaryTime >= PrimaryDuration)
		{
			// Exact connection into dead_front / dead_back without crossfade drift!
			SetPrimaryClipInternal(
				EMorphRigPrimaryState::DeadHeld,
				bDeathIsFront ? TEXT("dead_front") : TEXT("dead_back"),
				false,
				0.0f);
		}
		break;
	case EMorphRigPrimaryState::DeadHeld:
		PrimaryTime = 0.0f;
		break;
	case EMorphRigPrimaryState::Respawning:
		if (PrimaryTime >= PrimaryDuration)
		{
			SetPrimaryClipInternal(EMorphRigPrimaryState::Locomotion, TEXT("idle_combat"), true, 0.16f);
		}
		break;
	default:
		break;
	}
}

void UMorphRigAnimInstance::CheckAndFireMarkers(
	FName ClipId,
	float PrevTime,
	float CurrTime,
	bool bLoop,
	FName LayerName,
	uint64& InOutFiredMask,
	int32& InOutLoopIdx)
{
	int32 MetaIdx = INDEX_NONE;
	for (int32 i = 0; i < GMorphRigClipCount; ++i)
	{
		if (ClipId == GMorphRigClips[i].ClipId)
		{
			MetaIdx = i;
			break;
		}
	}
	if (MetaIdx == INDEX_NONE)
	{
		return;
	}

	const FMorphRigClipMeta& Meta = GMorphRigClips[MetaIdx];
	if (Meta.MarkerCount <= 0)
	{
		return;
	}

	const float Dur = FMath::Max(0.0333f, Meta.DurationSec);
	if (bLoop)
	{
		const int32 NewLoopIdx = FMath::FloorToInt(CurrTime / Dur);
		if (NewLoopIdx > InOutLoopIdx)
		{
			InOutLoopIdx = NewLoopIdx;
			InOutFiredMask = 0; // Reset bitmask cleanly once per loop cycle
		}
	}

	const float LocalPrev = bLoop ? FMath::Fmod(FMath::Max(0.0f, PrevTime), Dur) : PrevTime;
	const float LocalCurr = bLoop ? FMath::Fmod(FMath::Max(0.0f, CurrTime), Dur) : CurrTime;

	for (int32 m = 0; m < Meta.MarkerCount && m < 63; ++m)
	{
		const uint64 Bit = (1ULL << m);
		if (InOutFiredMask & Bit)
		{
			continue; // Already fired in this action/loop instance -> guaranteed deduplication!
		}
		const FMorphRigMarkerMeta& Marker = GMorphRigMarkers[Meta.MarkerOffset + m];
		const bool bCrossed = (LocalCurr >= LocalPrev)
			? (Marker.TimeSec >= LocalPrev - 1e-4f && Marker.TimeSec <= LocalCurr + 1e-4f)
			: (Marker.TimeSec >= LocalPrev || Marker.TimeSec <= LocalCurr);
		if (bCrossed)
		{
			InOutFiredMask |= Bit;
			EmitMarkerEvent(ClipId, FName(Marker.Name), LayerName, LocalCurr);
		}
	}
}

void UMorphRigAnimInstance::EmitMarkerEvent(FName ClipId, FName MarkerName, FName LayerName, float ClipTime)
{
	FMorphRigEventRecord Rec;
	Rec.WorldTimeSec = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f;
	Rec.ClipId = ClipId;
	Rec.MarkerName = MarkerName;
	Rec.LayerName = LayerName;
	Rec.ClipTimeSec = ClipTime;
	Rec.PlayRate = ActionPlayRate;

	RecentEvents.Insert(Rec, 0);
	if (RecentEvents.Num() > 28)
	{
		RecentEvents.SetNum(28);
	}
	OnMarkerFired.Broadcast(Rec);
}

void UMorphRigAnimInstance::UpdateGroundIKAndSprings(float DeltaSeconds)
{
	USkeletalMeshComponent* SkelComp = GetSkelMeshComponent();
	AActor* Owner = SkelComp ? SkelComp->GetOwner() : nullptr;
	UWorld* World = SkelComp ? SkelComp->GetWorld() : nullptr;
	if (!SkelComp || !Owner || !World || DeltaSeconds <= 1e-5f)
	{
		return;
	}

	// 1. Ground-Adaptation Foot & Pelvis Line Traces (handles flat floor, up to 20 deg ramp, and 20 cm steps)
	float TargetFootL = 0.0f, TargetFootR = 0.0f;
	FVector TargetNormCS_L = FVector::UpVector, TargetNormCS_R = FVector::UpVector;

	if (bEnableGroundIK && bIsGrounded && PrimaryState == EMorphRigPrimaryState::Locomotion)
	{
		const FTransform CompXform = SkelComp->GetComponentTransform();
		const float FloorBaseZ = CompXform.GetLocation().Z;

		auto TraceFoot = [&](FName BoneName, float& OutZOffset, FVector& OutNormalCS)
		{
			const FVector BoneWorld = SkelComp->GetBoneLocation(BoneName);
			const FVector Start(BoneWorld.X, BoneWorld.Y, FloorBaseZ + 65.0f);
			const FVector End(BoneWorld.X, BoneWorld.Y, FloorBaseZ - 45.0f);

			FCollisionQueryParams Params(SCENE_QUERY_STAT(MorphRigFootIK), false, Owner);
			FHitResult Hit;
			if (World->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params) && Hit.bBlockingHit)
			{
				OutZOffset = FMath::Clamp(Hit.ImpactPoint.Z - FloorBaseZ, -26.0f, 26.0f);
				OutNormalCS = CompXform.InverseTransformVectorNoScale(Hit.ImpactNormal).GetSafeNormal();
			}
		};

		TraceFoot(TEXT("foot_l"), TargetFootL, TargetNormCS_L);
		TraceFoot(TEXT("foot_r"), TargetFootR, TargetNormCS_R);
	}

	const float TargetPelvisZ = FMath::Min(TargetFootL, TargetFootR);
	const float InterpSpeed = 16.0f;
	FootOffsetZ_L = FMath::FInterpTo(FootOffsetZ_L, TargetFootL, DeltaSeconds, InterpSpeed);
	FootOffsetZ_R = FMath::FInterpTo(FootOffsetZ_R, TargetFootR, DeltaSeconds, InterpSpeed);
	PelvisOffsetZ = FMath::FInterpTo(PelvisOffsetZ, TargetPelvisZ, DeltaSeconds, 12.0f);
	FootNormalCS_L = FMath::VInterpNormalRotationTo(FootNormalCS_L, TargetNormCS_L, DeltaSeconds, 180.0f);
	FootNormalCS_R = FMath::VInterpNormalRotationTo(FootNormalCS_R, TargetNormCS_R, DeltaSeconds, 180.0f);

	// 2. Critically-Damped Spring Settle on Neural Cable & Hip Strap (no runaway!)
	const FVector CurrPos = Owner->GetActorLocation();
	const float CurrYaw = Owner->GetActorRotation().Yaw;
	if (!bPrevKinematicsValid)
	{
		PrevActorPos = CurrPos;
		PrevActorYaw = CurrYaw;
		bPrevKinematicsValid = true;
		return;
	}

	const FVector WorldVel = (CurrPos - PrevActorPos) / DeltaSeconds;
	const FVector LocalVel = Owner->GetActorTransform().InverseTransformVectorNoScale(WorldVel);
	const float YawRate = FMath::FindDeltaAngleDegrees(PrevActorYaw, CurrYaw) / DeltaSeconds;
	PrevActorPos = CurrPos;
	PrevActorYaw = CurrYaw;

	// External inertial target angle (clamped strictly to +-0.28 rad = +-16 deg)
	const FVector2D CableTarget(
		FMath::Clamp(-LocalVel.X * 0.00035f + FMath::Abs(WorldVel.Z) * 0.0003f, -0.26f, 0.26f),
		FMath::Clamp(-LocalVel.Y * 0.00030f - YawRate * 0.0006f, -0.24f, 0.24f));
	const FVector2D StrapTarget(
		FMath::Clamp(-LocalVel.X * 0.00028f, -0.22f, 0.22f),
		FMath::Clamp(FMath::Max(0.0f, LocalVel.Y * 0.00035f) + FMath::Abs(YawRate) * 0.0004f, -0.22f, 0.24f));

	auto StepSpring = [&](FVector2D& Pos, FVector2D& Vel, const FVector2D& Target, float Stiffness, float Damping)
	{
		const FVector2D Acc = (Target - Pos) * Stiffness - Vel * Damping;
		Vel += Acc * DeltaSeconds;
		Pos += Vel * DeltaSeconds;
		Pos.X = FMath::Clamp(Pos.X, -0.32f, 0.32f);
		Pos.Y = FMath::Clamp(Pos.Y, -0.32f, 0.32f);
	};

	StepSpring(CableSpringPos, CableSpringVel, CableTarget, 110.0f, 16.0f);
	StepSpring(StrapSpringPos, StrapSpringVel, StrapTarget, 95.0f, 14.5f);
}

// ============================================================================
// HIGH-LEVEL ACTION & INTERRUPT TRIGGERS
// ============================================================================

bool UMorphRigAnimInstance::TriggerDash(FName DirectionSuffix)
{
	if (IsTerminalDead() || bRooted || bStasis || GetStatePriority(PrimaryState) > 30)
	{
		return false;
	}
	const FString FullName = FString::Printf(TEXT("dash_%s"), *DirectionSuffix.ToString());
	SetPrimaryClipInternal(EMorphRigPrimaryState::MobilityDash, FName(*FullName), false, 0.08f);
	return true;
}

bool UMorphRigAnimInstance::TriggerBlink()
{
	if (IsTerminalDead() || bRooted || bSilenced || bStasis || GetStatePriority(PrimaryState) > 30)
	{
		return false;
	}
	SetPrimaryClipInternal(EMorphRigPrimaryState::MobilityBlink, TEXT("blink_out"), false, 0.06f);
	return true;
}

bool UMorphRigAnimInstance::TriggerMeleeAttack()
{
	if (IsTerminalDead() || bDisarmed || bStasis)
	{
		return false;
	}
	if (PrimaryState == EMorphRigPrimaryState::AbilityOneShot && MeleeComboIndex >= 1 && MeleeComboIndex < 3)
	{
		bMeleeQueuedNext = true;
		return true;
	}
	if (GetStatePriority(PrimaryState) > 20)
	{
		return false;
	}
	MeleeComboIndex = 1;
	bMeleeQueuedNext = false;
	SetPrimaryClipInternal(EMorphRigPrimaryState::AbilityOneShot, TEXT("melee_1"), false, 0.10f);
	return true;
}

bool UMorphRigAnimInstance::TriggerUpperBodyAction(EMorphRigUpperBodyMode Mode)
{
	if (IsTerminalDead() || bStasis)
	{
		return false;
	}
	if ((Mode == EMorphRigUpperBodyMode::RangedFire || Mode == EMorphRigUpperBodyMode::RangedBurst || Mode == EMorphRigUpperBodyMode::Reload) && bDisarmed)
	{
		return false;
	}
	if (Mode == EMorphRigUpperBodyMode::CastDirectional && bSilenced)
	{
		return false;
	}
	if (PrimaryState != EMorphRigPrimaryState::Locomotion)
	{
		return false;
	}

	FName Clip = NAME_None;
	switch (Mode)
	{
	case EMorphRigUpperBodyMode::RangedFire:      Clip = TEXT("ranged_fire"); break;
	case EMorphRigUpperBodyMode::RangedBurst:     Clip = TEXT("ranged_burst"); break;
	case EMorphRigUpperBodyMode::Reload:          Clip = TEXT("reload"); break;
	case EMorphRigUpperBodyMode::CastDirectional: Clip = TEXT("cast_directional"); break;
	default: return false;
	}

	UpperBodyMode = Mode;
	UpperClip = Clip;
	UpperTime = 0.0f;
	UpperWeight = 0.25f;
	UpperInstanceCounter++;
	FiredUpperMask = 0;
	return true;
}

bool UMorphRigAnimInstance::TriggerReload()
{
	if (IsTerminalDead() || bDisarmed || bStasis)
	{
		return false;
	}
	if (PrimaryState == EMorphRigPrimaryState::Locomotion && GroundSpeed > 15.0f)
	{
		return TriggerUpperBodyAction(EMorphRigUpperBodyMode::Reload);
	}
	if (GetStatePriority(PrimaryState) > 20)
	{
		return false;
	}
	SetPrimaryClipInternal(EMorphRigPrimaryState::AbilityOneShot, TEXT("reload"), false, 0.14f);
	return true;
}

bool UMorphRigAnimInstance::TriggerCastGround()
{
	if (IsTerminalDead() || bSilenced || bStasis || GetStatePriority(PrimaryState) > 20) { return false; }
	SetPrimaryClipInternal(EMorphRigPrimaryState::AbilityOneShot, TEXT("cast_ground"), false, 0.14f);
	return true;
}

bool UMorphRigAnimInstance::TriggerCastSelf()
{
	if (IsTerminalDead() || bSilenced || bStasis || GetStatePriority(PrimaryState) > 20) { return false; }
	SetPrimaryClipInternal(EMorphRigPrimaryState::AbilityOneShot, TEXT("cast_self"), false, 0.14f);
	return true;
}

bool UMorphRigAnimInstance::TriggerDeploy()
{
	if (IsTerminalDead() || bSilenced || bStasis || GetStatePriority(PrimaryState) > 20) { return false; }
	SetPrimaryClipInternal(EMorphRigPrimaryState::AbilityOneShot, TEXT("deploy"), false, 0.16f);
	return true;
}

bool UMorphRigAnimInstance::TriggerSocialOrDialogue(FName ClipId)
{
	if (IsTerminalDead() || bStasis || GetStatePriority(PrimaryState) > 20) { return false; }
	SetPrimaryClipInternal(EMorphRigPrimaryState::AbilityOneShot, ClipId, false, 0.18f);
	return true;
}

bool UMorphRigAnimInstance::StartChannel(float AutoCompleteAfterSec)
{
	if (IsTerminalDead() || bSilenced || bStasis || GetStatePriority(PrimaryState) > 20) { return false; }
	SustainedAutoFinishTime = AutoCompleteAfterSec;
	SustainedHoldTimer = 0.0f;
	SetPrimaryClipInternal(EMorphRigPrimaryState::ChannelStart, TEXT("channel_start"), false, 0.14f);
	return true;
}

bool UMorphRigAnimInstance::FinishChannel()
{
	if (PrimaryState != EMorphRigPrimaryState::ChannelStart && PrimaryState != EMorphRigPrimaryState::ChannelLoop)
	{
		return false;
	}
	SetPrimaryClipInternal(EMorphRigPrimaryState::ChannelEnd, TEXT("channel_end"), false, 0.14f);
	return true;
}

bool UMorphRigAnimInstance::InterruptChannel()
{
	if (PrimaryState != EMorphRigPrimaryState::ChannelStart && PrimaryState != EMorphRigPrimaryState::ChannelLoop)
	{
		return false;
	}
	// Arbitrary-point pose-snapshot crossfade into channel_interrupt — never snaps back to frame 0!
	SetPrimaryClipInternal(EMorphRigPrimaryState::ChannelInterrupt, TEXT("channel_interrupt"), false, 0.14f);
	return true;
}

bool UMorphRigAnimInstance::StartCharge()
{
	if (IsTerminalDead() || bSilenced || bStasis || GetStatePriority(PrimaryState) > 20) { return false; }
	SustainedHoldTimer = 0.0f;
	SetPrimaryClipInternal(EMorphRigPrimaryState::ChargeStart, TEXT("charge_start"), false, 0.14f);
	return true;
}

bool UMorphRigAnimInstance::ReleaseCharge()
{
	if (PrimaryState != EMorphRigPrimaryState::ChargeStart && PrimaryState != EMorphRigPrimaryState::ChargeHold)
	{
		return false;
	}
	SetPrimaryClipInternal(EMorphRigPrimaryState::ChargeRelease, TEXT("charge_release"), false, 0.12f);
	return true;
}

bool UMorphRigAnimInstance::CancelCharge()
{
	if (PrimaryState != EMorphRigPrimaryState::ChargeStart && PrimaryState != EMorphRigPrimaryState::ChargeHold)
	{
		return false;
	}
	SetPrimaryClipInternal(EMorphRigPrimaryState::ChargeCancel, TEXT("charge_cancel"), false, 0.15f);
	return true;
}

bool UMorphRigAnimInstance::StartUplink(float AutoCompleteAfterSec)
{
	if (IsTerminalDead() || bSilenced || bStasis || GetStatePriority(PrimaryState) > 20) { return false; }
	SustainedAutoFinishTime = AutoCompleteAfterSec;
	SustainedHoldTimer = 0.0f;
	SetPrimaryClipInternal(EMorphRigPrimaryState::UplinkStart, TEXT("uplink_start"), false, 0.16f);
	return true;
}

bool UMorphRigAnimInstance::FinishUplink()
{
	if (PrimaryState != EMorphRigPrimaryState::UplinkStart && PrimaryState != EMorphRigPrimaryState::UplinkLoop)
	{
		return false;
	}
	SetPrimaryClipInternal(EMorphRigPrimaryState::UplinkEnd, TEXT("uplink_end"), false, 0.14f);
	return true;
}

bool UMorphRigAnimInstance::CancelUplink()
{
	if (PrimaryState != EMorphRigPrimaryState::UplinkStart && PrimaryState != EMorphRigPrimaryState::UplinkLoop)
	{
		return false;
	}
	SetPrimaryClipInternal(EMorphRigPrimaryState::UplinkCancel, TEXT("uplink_cancel"), false, 0.15f);
	return true;
}

bool UMorphRigAnimInstance::TriggerLocoTransition(FName ClipId)
{
	if (PrimaryState != EMorphRigPrimaryState::Locomotion || bStasis)
	{
		return false;
	}
	RequestSnapshotCrossfade(0.10f);
	LocoSubClip = ClipId;
	LocoSubTime = 0.0f;
	LocoSubWeight = 1.0f;
	bLocoSubLoop = false;
	LocoSubInstanceCounter++;
	FiredLocoSubMask = 0;
	return true;
}

bool UMorphRigAnimInstance::TriggerJump()
{
	if (PrimaryState != EMorphRigPrimaryState::Locomotion || bRooted || bStasis || !bIsGrounded)
	{
		return false;
	}
	RequestSnapshotCrossfade(0.08f);
	LocoSubClip = TEXT("jump_start");
	LocoSubTime = 0.0f;
	LocoSubWeight = 1.0f;
	bLocoSubLoop = false;
	FiredLocoSubMask = 0;
	return true;
}

void UMorphRigAnimInstance::TriggerAdditiveHit(FName DirectionSuffix)
{
	if (IsTerminalDead())
	{
		return;
	}
	// Damage wakes sleep cleanly
	if (PrimaryState == EMorphRigPrimaryState::DisableSleepLoop || PrimaryState == EMorphRigPrimaryState::DisableSleepStart)
	{
		WakeFromSleep();
	}
	HitClip = FName(*FString::Printf(TEXT("hit_%s"), *DirectionSuffix.ToString()));
	HitTime = 0.0f;
	HitWeight = 1.0f;
}

bool UMorphRigAnimInstance::TriggerStun(float HoldDuration)
{
	if (IsTerminalDead()) { return false; }
	SustainedAutoFinishTime = HoldDuration;
	SetPrimaryClipInternal(EMorphRigPrimaryState::DisableStunStart, TEXT("stun_start"), false, 0.14f);
	return true;
}

bool UMorphRigAnimInstance::TriggerSleep(float HoldDuration)
{
	if (IsTerminalDead()) { return false; }
	SustainedAutoFinishTime = HoldDuration;
	SetPrimaryClipInternal(EMorphRigPrimaryState::DisableSleepStart, TEXT("sleep_start"), false, 0.18f);
	return true;
}

bool UMorphRigAnimInstance::WakeFromSleep()
{
	if (PrimaryState != EMorphRigPrimaryState::DisableSleepStart && PrimaryState != EMorphRigPrimaryState::DisableSleepLoop)
	{
		return false;
	}
	SetPrimaryClipInternal(EMorphRigPrimaryState::DisableSleepEnd, TEXT("sleep_end"), false, 0.16f);
	return true;
}

bool UMorphRigAnimInstance::TriggerKnockback()
{
	if (IsTerminalDead()) { return false; }
	SetPrimaryClipInternal(EMorphRigPrimaryState::DisableKnockback, TEXT("knockback"), false, 0.10f);
	return true;
}

bool UMorphRigAnimInstance::TriggerKnockup(bool bLandFront)
{
	if (IsTerminalDead()) { return false; }
	bKnockdownIsFront = bLandFront;
	SustainedHoldTimer = 0.0f;
	SetPrimaryClipInternal(EMorphRigPrimaryState::DisableKnockupStart, TEXT("knockup_start"), false, 0.10f);
	return true;
}

bool UMorphRigAnimInstance::TriggerKnockdown(bool bFront, float ProneDuration)
{
	if (IsTerminalDead()) { return false; }
	bKnockdownIsFront = bFront;
	SustainedAutoFinishTime = ProneDuration;
	SetPrimaryClipInternal(
		EMorphRigPrimaryState::DisableKnockdown,
		bFront ? TEXT("knockdown_front") : TEXT("knockdown_back"),
		false,
		0.12f);
	return true;
}

bool UMorphRigAnimInstance::TriggerGetup()
{
	if (PrimaryState != EMorphRigPrimaryState::DisableProne && PrimaryState != EMorphRigPrimaryState::DisableKnockdown)
	{
		return false;
	}
	SetPrimaryClipInternal(
		EMorphRigPrimaryState::DisableGetup,
		bKnockdownIsFront ? TEXT("getup_front") : TEXT("getup_back"),
		false,
		0.10f);
	return true;
}

bool UMorphRigAnimInstance::TriggerDeath(bool bFrontImpact)
{
	// Death overrides all nonterminal actions and occurs ONCE!
	if (IsTerminalDead())
	{
		return false;
	}
	bStasis = false;
	bDeathIsFront = bFrontImpact;
	HitClip = NAME_None;
	HitWeight = 0.0f;
	SetPrimaryClipInternal(
		EMorphRigPrimaryState::DeathDying,
		bFrontImpact ? TEXT("death_front") : TEXT("death_back"),
		false,
		0.14f);
	return true;
}

bool UMorphRigAnimInstance::TriggerRespawn()
{
	if (!IsTerminalDead() && PrimaryState != EMorphRigPrimaryState::DirectClipInspect)
	{
		return false;
	}
	bWounded = false;
	bRooted = false;
	bSilenced = false;
	bDisarmed = false;
	bFeared = false;
	bCharmed = false;
	bTaunted = false;
	bStasis = false;
	SetPrimaryClipInternal(EMorphRigPrimaryState::Respawning, TEXT("respawn"), false, 0.10f);
	return true;
}

void UMorphRigAnimInstance::PlayDirectClip(FName ClipId)
{
	bStasis = false;
	const bool bLoop = IsClipLooping(ClipId);
	SetPrimaryClipInternal(EMorphRigPrimaryState::DirectClipInspect, ClipId, bLoop, 0.12f);
}

void UMorphRigAnimInstance::ExitDirectClipMode()
{
	SetPrimaryClipInternal(EMorphRigPrimaryState::Locomotion, TEXT("idle_combat"), true, 0.14f);
}

FVector UMorphRigAnimInstance::ConsumeDashRootDeltaCm(float PrevTime, float CurrTime, FName DashClipId) const
{
	const float Dur = FMath::Max(0.1f, GetClipDuration(DashClipId));
	const float U0 = FMath::Clamp(PrevTime / Dur, 0.0f, 1.0f);
	const float U1 = FMath::Clamp(CurrTime / Dur, 0.0f, 1.0f);
	// Matches exact smoothstep(0.08, 0.88, u) * 200.0 cm authored in motion_library.py!
	auto EvalSmooth = [](float U) -> float
	{
		const float T = FMath::Clamp((U - 0.08f) / 0.80f, 0.0f, 1.0f);
		return T * T * (3.0f - 2.0f * T) * 200.0f;
	};
	const float DeltaDist = FMath::Max(0.0f, EvalSmooth(U1) - EvalSmooth(U0));
	if (DashClipId == TEXT("dash_f")) { return FVector(DeltaDist, 0.0f, 0.0f); }
	if (DashClipId == TEXT("dash_b")) { return FVector(-DeltaDist, 0.0f, 0.0f); }
	if (DashClipId == TEXT("dash_l")) { return FVector(0.0f, -DeltaDist, 0.0f); }
	if (DashClipId == TEXT("dash_r")) { return FVector(0.0f, +DeltaDist, 0.0f); }
	return FVector::ZeroVector;
}
