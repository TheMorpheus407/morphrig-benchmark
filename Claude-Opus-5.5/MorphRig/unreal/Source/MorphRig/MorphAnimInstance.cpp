#include "MorphAnimInstance.h"

#include "Animation/AnimSequence.h"
#include "Animation/AnimationPoseData.h"
#include "Animation/AnimCurveElementFlags.h"
#include "AnimationRuntime.h"
#include "BonePose.h"
#include "TwoBoneIK.h"

namespace
{
	const TCHAR* LegThigh[2] = {TEXT("thigh_l"), TEXT("thigh_r")};
	const TCHAR* LegCalf[2] = {TEXT("calf_l"), TEXT("calf_r")};
	const TCHAR* LegFoot[2] = {TEXT("foot_l"), TEXT("foot_r")};
}

void FMorphAnimProxy::Initialize(UAnimInstance* InAnimInstance)
{
	FAnimInstanceProxy::Initialize(InAnimInstance);
	bMasksReady = false;
}

void FMorphAnimProxy::PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds)
{
	FAnimInstanceProxy::PreUpdate(InAnimInstance, DeltaSeconds);
	Req = CastChecked<UMorphAnimInstance>(InAnimInstance)->Request;
}

void FMorphAnimProxy::BuildMasks()
{
	const FReferenceSkeleton& Ref = GetRequiredBones().GetReferenceSkeleton();
	const int32 N = Ref.GetNum();
	UpperMask.Init(0.f, N);
	AimMask.Init(0.f, N);
	auto Find = [&Ref](const TCHAR* Name) { return Ref.FindBoneIndex(FName(Name)); };
	const int32 Spine1 = Find(TEXT("spine_01"));
	const int32 Spine2 = Find(TEXT("spine_02"));
	const int32 Spine3 = Find(TEXT("spine_03"));
	for (int32 i = 0; i < N; ++i)
	{
		// walk up to classify the bone
		float Up = 0.f, Aim = 0.f;
		for (int32 b = i; b != INDEX_NONE; b = Ref.GetParentIndex(b))
		{
			if (b == Spine3) { Up = FMath::Max(Up, 1.f); Aim = FMath::Max(Aim, 1.f); break; }
			if (b == Spine2 && b == i) { Up = 0.7f; Aim = 0.5f; break; }
			if (b == Spine1 && b == i) { Up = 0.35f; Aim = 0.15f; break; }
		}
		UpperMask[i] = Up;
		AimMask[i] = Aim;
	}
	MeshPelvis = Find(TEXT("pelvis"));
	for (int32 s = 0; s < 2; ++s)
	{
		MeshThigh[s] = Find(LegThigh[s]);
		MeshCalf[s] = Find(LegCalf[s]);
		MeshFoot[s] = Find(LegFoot[s]);
	}
	MeshNeck = Find(TEXT("neck_01"));
	MeshHead = Find(TEXT("head"));
	bMasksReady = true;
}

void FMorphAnimProxy::Sample(const FMorphTrack& T, FPoseContext& Out) const
{
	FAnimationPoseData Data(Out);
	const FAnimExtractContext Ctx(double(T.Time), T.bLockRoot, FDeltaTimeRecord(), T.bLoop);
	T.Seq->GetAnimationPose(Data, Ctx);
}

void FMorphAnimProxy::BlendStack(TConstArrayView<FMorphTrack> Tracks, FPoseContext& Out) const
{
	float Total = 0.f;
	int32 Valid = 0;
	for (const FMorphTrack& T : Tracks)
	{
		if (T.Seq && T.Weight > 1e-4f) { Total += T.Weight; ++Valid; }
	}
	if (Valid == 0)
	{
		Out.ResetToRefPose();
		return;
	}
	if (Valid == 1)
	{
		for (const FMorphTrack& T : Tracks)
		{
			if (T.Seq && T.Weight > 1e-4f) { Sample(T, Out); return; }
		}
	}
	// accumulate: first sample into Out, blend the others in place with running weights
	float Acc = 0.f;
	bool bFirst = true;
	for (const FMorphTrack& T : Tracks)
	{
		if (!T.Seq || T.Weight <= 1e-4f)
		{
			continue;
		}
		const float W = T.Weight / Total;
		if (bFirst)
		{
			Sample(T, Out);
			Acc = W;
			bFirst = false;
			continue;
		}
		FPoseContext Tmp(Out);
		Sample(T, Tmp);
		const float Keep = Acc / (Acc + W);           // weight of what is already in Out
		FAnimationPoseData OutData(Out);
		const FAnimationPoseData TmpData(Tmp);
		FAnimationRuntime::BlendTwoPosesTogetherInPlace(OutData, TmpData, Keep);
		Acc += W;
	}
}

void FMorphAnimProxy::MaskedBlend(FPoseContext& InOut, const FPoseContext& Other, const TArray<float>& Mask,
                                  float Alpha) const
{
	const FBoneContainer& BC = InOut.Pose.GetBoneContainer();
	for (const FCompactPoseBoneIndex I : InOut.Pose.ForEachBoneIndex())
	{
		const int32 Mesh = BC.MakeMeshPoseIndex(I).GetInt();
		const float W = Mask.IsValidIndex(Mesh) ? Mask[Mesh] * Alpha : 0.f;
		if (W > 1e-4f)
		{
			FTransform& A = InOut.Pose[I];
			const FTransform& B = Other.Pose[I];
			A.BlendWith(B, W);
		}
	}
	InOut.Curve.LerpTo(Other.Curve, Alpha);
}

void FMorphAnimProxy::ApplyLegIK(FPoseContext& Output) const
{
	const FMorphLegIK& IK = Req.LegIK;
	if (IK.Alpha <= 1e-3f || MeshPelvis == INDEX_NONE)
	{
		return;
	}
	const FBoneContainer& BC = Output.Pose.GetBoneContainer();
	auto C = [&BC](int32 MeshIdx) { return BC.MakeCompactPoseIndex(FMeshPoseBoneIndex(MeshIdx)); };
	FCSPose<FCompactPose> CS;
	CS.InitPose(Output.Pose);
	// remember animated ankle positions before moving the pelvis
	FVector Ankle[2];
	FVector KneeDir[2];
	for (int32 s = 0; s < 2; ++s)
	{
		Ankle[s] = CS.GetComponentSpaceTransform(C(MeshFoot[s])).GetLocation();
		const FVector Hip = CS.GetComponentSpaceTransform(C(MeshThigh[s])).GetLocation();
		const FVector Knee = CS.GetComponentSpaceTransform(C(MeshCalf[s])).GetLocation();
		KneeDir[s] = (Knee - (Hip + Ankle[s]) * 0.5f).GetSafeNormal();
	}
	// pelvis down so the lower foot can reach its ground
	{
		FTransform P = CS.GetComponentSpaceTransform(C(MeshPelvis));
		P.AddToTranslation(FVector(0, 0, IK.PelvisOffset * IK.Alpha));
		TArray<FBoneTransform> Set;
		Set.Add(FBoneTransform(C(MeshPelvis), P));
		CS.SafeSetCSBoneTransforms(Set);
	}
	for (int32 s = 0; s < 2; ++s)
	{
		FTransform Thigh = CS.GetComponentSpaceTransform(C(MeshThigh[s]));
		FTransform Calf = CS.GetComponentSpaceTransform(C(MeshCalf[s]));
		FTransform Foot = CS.GetComponentSpaceTransform(C(MeshFoot[s]));
		const FVector Target = Ankle[s] + FVector(0, 0, IK.FootOffset[s] * IK.Alpha);
		const FVector Pole = Calf.GetLocation() + KneeDir[s] * 40.f;
		const FQuat FootRot = Foot.GetRotation();
		AnimationCore::SolveTwoBoneIK(Thigh, Calf, Foot, Pole, Target, false, 1.0, 1.0);
		// align the sole to the ground normal (limited tilt)
		FVector Nrm = IK.GroundNormal[s].GetSafeNormal();
		if (Nrm.IsNearlyZero()) { Nrm = FVector::UpVector; }
		const FQuat Tilt = FQuat::FindBetweenNormals(FVector::UpVector, Nrm);
		const FQuat Blended = FQuat::Slerp(FQuat::Identity, Tilt, IK.Alpha);
		Foot.SetRotation(Blended * FootRot);
		TArray<FBoneTransform> Set;
		Set.Add(FBoneTransform(C(MeshThigh[s]), Thigh));
		Set.Add(FBoneTransform(C(MeshCalf[s]), Calf));
		Set.Add(FBoneTransform(C(MeshFoot[s]), Foot));
		CS.SafeSetCSBoneTransforms(Set);
	}
	FCSPose<FCompactPose>::ConvertComponentPosesToLocalPoses(CS, Output.Pose);
}

void FMorphAnimProxy::ApplyLookAt(FPoseContext& Output) const
{
	if (Req.LookAlpha <= 1e-3f || MeshHead == INDEX_NONE || MeshNeck == INDEX_NONE)
	{
		return;
	}
	const FBoneContainer& BC = Output.Pose.GetBoneContainer();
	FCSPose<FCompactPose> CS;
	CS.InitPose(Output.Pose);
	const float Yaw = FMath::DegreesToRadians(FMath::Clamp(Req.LookYaw, -70.f, 70.f)) * Req.LookAlpha;
	const float Pitch = FMath::DegreesToRadians(FMath::Clamp(Req.LookPitch, -40.f, 40.f)) * Req.LookAlpha;
	// mesh space: +Y is the character's forward, +Z up -> pitch axis is X
	const TPair<int32, float> Chain[2] = {{MeshNeck, 0.4f}, {MeshHead, 0.6f}};
	for (const TPair<int32, float>& L : Chain)
	{
		const FCompactPoseBoneIndex I = BC.MakeCompactPoseIndex(FMeshPoseBoneIndex(L.Key));
		FTransform T = CS.GetComponentSpaceTransform(I);
		const FQuat Q = FQuat(FVector::UpVector, Yaw * L.Value) * FQuat(FVector::XAxisVector, -Pitch * L.Value);
		T.SetRotation(Q * T.GetRotation());
		TArray<FBoneTransform> Set;
		Set.Add(FBoneTransform(I, T));
		CS.SafeSetCSBoneTransforms(Set);
	}
	FCSPose<FCompactPose>::ConvertComponentPosesToLocalPoses(CS, Output.Pose);
}

bool FMorphAnimProxy::Evaluate(FPoseContext& Output)
{
	if (!bMasksReady)
	{
		BuildMasks();
	}
	BlendStack(Req.Base, Output);
	if (Req.UpperAlpha > 1e-3f && Req.Upper.Num())
	{
		FPoseContext Up(Output);
		BlendStack(Req.Upper, Up);
		MaskedBlend(Output, Up, UpperMask, Req.UpperAlpha);
	}
	if (Req.AimAlpha > 1e-3f && Req.Aim.Num())
	{
		FPoseContext AimPose(Output);
		BlendStack(Req.Aim, AimPose);
		MaskedBlend(Output, AimPose, AimMask, Req.AimAlpha);
	}
	for (const FMorphTrack& T : Req.Additive)
	{
		if (!T.Seq || T.Weight <= 1e-4f)
		{
			continue;
		}
		FPoseContext Add(this, true);
		Sample(T, Add);
		FAnimationPoseData OutData(Output);
		const FAnimationPoseData AddData(Add);
		FAnimationRuntime::AccumulateAdditivePose(OutData, AddData, T.Weight, AAT_LocalSpaceBase);
	}
	Output.Pose.NormalizeRotations();
	ApplyLookAt(Output);
	ApplyLegIK(Output);
	if (Req.MorphAlpha > 1e-3f)
	{
		for (const TPair<FName, float>& M : Req.Morphs)
		{
			const float Cur = Output.Curve.Get(M.Key);
			Output.Curve.Set(M.Key, FMath::Lerp(Cur, M.Value, Req.MorphAlpha));
			Output.Curve.SetFlags(M.Key, UE::Anim::ECurveElementFlags::MorphTarget);
		}
	}
	return true;
}
