#include "OperativeAnimInstance.h"
#include "MorphRig.h"
#include "MorphRigData.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimationPoseData.h"
#include "Animation/AttributesRuntime.h"
#include "AnimationRuntime.h"
#include "BonePose.h"
#include "TwoBoneIK.h"
#include "Components/SkeletalMeshComponent.h"

namespace
{
	const FName BN_Spine01(TEXT("spine_01"));
	const FName BN_Spine02(TEXT("spine_02"));
	const FName BN_Spine03(TEXT("spine_03"));
	const FName BN_Pelvis(TEXT("pelvis"));
	const FName BN_Root(TEXT("root"));
	const FName BN_Head(TEXT("head"));
	const FName BN_Neck(TEXT("neck_01"));
	const FVector CS_FORWARD(0.0, 1.0, 0.0);   // component space: mesh faces +Y
	const FVector CS_LEFT(1.0, 0.0, 0.0);
	const FVector CS_UP(0.0, 0.0, 1.0);
	const FVector BONE_AXIS(0.0, 1.0, 0.0);    // twist axis in bone space (bones run along local -Y)

	/** Quintic inertialization curve (same polynomial as the engine's inertialization node). */
	float InertialFloat(float x0, float v0, float t, float t1)
	{
		const float Eps = 1.0e-7f;
		if (t < 0.f)
		{
			t = 0.f;
		}
		if (t >= t1 - Eps)
		{
			return 0.f;
		}
		float Sign = 1.f;
		if (x0 < 0.f)
		{
			x0 = -x0;
			v0 = -v0;
			Sign = -1.f;
		}
		if (v0 > 0.f)
		{
			v0 = 0.f;
		}
		if (v0 < -UE_KINDA_SMALL_NUMBER)
		{
			t1 = FMath::Min(t1, -5.f * x0 / v0);
		}
		if (t >= t1 - Eps)
		{
			return 0.f;
		}
		const float t1_2 = t1 * t1;
		const float t1_3 = t1 * t1_2;
		const float t1_4 = t1 * t1_3;
		const float t1_5 = t1 * t1_4;
		const float a0 = FMath::Max(0.f, (-8.f * t1 * v0 - 20.f * x0) / t1_2);
		const float A = -(a0 * t1_2 + 6.f * t1 * v0 + 12.f * x0) / (2.f * t1_5);
		const float B = (3.f * a0 * t1_2 + 16.f * t1 * v0 + 30.f * x0) / (2.f * t1_4);
		const float Cc = -(3.f * a0 * t1_2 + 12.f * t1 * v0 + 20.f * x0) / (2.f * t1_3);
		const float x = ((((A * t + B) * t + Cc) * t + 0.5f * a0) * t + v0) * t + x0;
		return Sign * x;
	}

	FQuat SlerpFromIdentity(const FQuat& Q, float Alpha)
	{
		return FQuat::Slerp(FQuat::Identity, Q, Alpha).GetNormalized();
	}

	void SampleSequence(const UAnimSequence* Seq, float Time, bool bLoop, FCompactPose& Pose, FBlendedCurve& Curve)
	{
		UE::Anim::FStackAttributeContainer Attributes;
		FAnimationPoseData Data(Pose, Curve, Attributes);
		const float Len = Seq->GetPlayLength();
		const float T = bLoop && Len > 0.f ? FMath::Fmod(FMath::Max(Time, 0.f), Len) : FMath::Clamp(Time, 0.f, Len);
		FAnimExtractContext Ctx((double)T, Seq->bEnableRootMotion, FDeltaTimeRecord(), bLoop);
		Seq->GetAnimationPose(Data, Ctx);
	}
}

// ------------------------------------------------------------------------------------------------ instance
UOperativeAnimInstance::UOperativeAnimInstance()
{
	RootMotionMode = ERootMotionMode::NoRootMotionExtraction;
}

void UOperativeAnimInstance::NativeInitializeAnimation()
{
	Super::NativeInitializeAnimation();
	const FMorphRigData& Data = FMorphRigData::Get();
	Sequences.Reset();
	Config.AimPoses.Reset();
	Config.HitClips.Reset();
	static const FName NAME_Aim(TEXT("aim"));
	static const FName NAME_Additive(TEXT("additive"));
	for (const FMorphClip& Clip : Data.Clips)
	{
		UAnimSequence* Seq = LoadObject<UAnimSequence>(nullptr, *Clip.AssetPath);
		if (!Seq)
		{
			UE_LOG(LogMorphRig, Error, TEXT("Missing animation asset %s"), *Clip.AssetPath);
			continue;
		}
		Sequences.Add(Clip.Id, Seq);
		if (Clip.Layer == NAME_Aim)
		{
			FOpAimPose P;
			P.Seq = Seq;
			P.YawDeg = Clip.AimYawDeg;
			P.PitchDeg = Clip.AimPitchDeg;
			Config.AimPoses.Add(P);
		}
		else if (Clip.Layer == NAME_Additive)
		{
			Config.HitClips.Add(Seq);
		}
	}
	++Config.Serial;
}

UAnimSequence* UOperativeAnimInstance::GetSequence(FName Id) const
{
	const TObjectPtr<UAnimSequence>* S = Sequences.Find(Id);
	return S ? S->Get() : nullptr;
}

FAnimInstanceProxy* UOperativeAnimInstance::CreateAnimInstanceProxy()
{
	return new FOperativeAnimProxy(this);
}

void UOperativeAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy)
{
	delete static_cast<FOperativeAnimProxy*>(InProxy);
}

// ------------------------------------------------------------------------------------------------ proxy
void FOperativeAnimProxy::PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds)
{
	FAnimInstanceProxy::PreUpdate(InAnimInstance, DeltaSeconds);
	if (const UOperativeAnimInstance* Inst = Cast<UOperativeAnimInstance>(InAnimInstance))
	{
		In = Inst->Input;
		if (Cfg.Serial != Inst->Config.Serial)
		{
			Cfg = Inst->Config;
		}
	}
}

void FOperativeAnimProxy::EnsureCache(const FBoneContainer& RB)
{
	if (CachedSerial == RB.GetSerialNumber() && CachedConfigSerial == Cfg.Serial && NumBones == RB.GetCompactPoseNumBones())
	{
		return;
	}
	CachedSerial = RB.GetSerialNumber();
	CachedConfigSerial = Cfg.Serial;
	NumBones = RB.GetCompactPoseNumBones();
	const FMorphRigData& Data = FMorphRigData::Get();
	const FReferenceSkeleton& RefSkel = RB.GetReferenceSkeleton();

	BoneMap.Reset();
	Parent.SetNum(NumBones);
	RefLocal.SetNum(NumBones);
	for (int32 i = 0; i < NumBones; ++i)
	{
		const FCompactPoseBoneIndex CI(i);
		Parent[i] = RB.GetParentBoneIndex(CI).GetInt();
		RefLocal[i] = RB.GetRefPoseTransform(CI);
		const int32 MeshIndex = RB.MakeMeshPoseIndex(CI).GetInt();
		BoneMap.Add(RefSkel.GetBoneName(MeshIndex), i);
	}
	ComputeCS(RefLocal, RefCS);

	// ---- masks
	UpperWeight.Init(0.f, NumBones);
	HitWeight.Init(0.f, NumBones);
	AimMask.Init(0, NumBones);
	const int32 S1 = Bone(BN_Spine01), S2 = Bone(BN_Spine02), S3 = Bone(BN_Spine03);
	for (int32 i = 0; i < NumBones; ++i)
	{
		const int32 P = Parent[i];
		if (i == S1)
		{
			UpperWeight[i] = 0.35f;
			AimMask[i] = 1;
		}
		else if (i == S2)
		{
			UpperWeight[i] = 0.7f;
			AimMask[i] = 1;
		}
		else if (i == S3)
		{
			UpperWeight[i] = 1.f;
			AimMask[i] = 1;
		}
		else if (P >= 0)
		{
			UpperWeight[i] = UpperWeight[P] >= 0.999f ? 1.f : 0.f;
			AimMask[i] = AimMask[P];
		}
	}
	for (const FName& PropName : Data.PropBones)
	{
		const int32 PropIdx = Bone(PropName);
		if (PropIdx != INDEX_NONE)
		{
			UpperWeight[PropIdx] = 1.f;   // prop motion always comes from the manipulating (upper) clip
			AimMask[PropIdx] = 0;
		}
	}
	for (const TCHAR* N : { TEXT("spine_01"), TEXT("spine_02"), TEXT("spine_03"), TEXT("neck_01"), TEXT("head"),
		TEXT("clavicle_l"), TEXT("clavicle_r"), TEXT("upperarm_l"), TEXT("upperarm_r") })
	{
		const int32 I = Bone(FName(N));
		if (I != INDEX_NONE)
		{
			HitWeight[I] = 1.f;
		}
	}

	// ---- named bones
	PelvisIdx = Bone(BN_Pelvis);
	RootIdx = Bone(BN_Root);
	HeadIdx = Bone(BN_Head);
	NeckIdx = Bone(BN_Neck);
	ChestIdx = S3;
	const TCHAR* Sides[2] = { TEXT("l"), TEXT("r") };
	for (int32 s = 0; s < 2; ++s)
	{
		Legs[s].Thigh = Bone(FName(*FString::Printf(TEXT("thigh_%s"), Sides[s])));
		Legs[s].Calf = Bone(FName(*FString::Printf(TEXT("calf_%s"), Sides[s])));
		Legs[s].Foot = Bone(FName(*FString::Printf(TEXT("foot_%s"), Sides[s])));
		EyeIdx[s] = Bone(FName(*FString::Printf(TEXT("eye_%s"), Sides[s])));
		LidUpperIdx[s] = Bone(FName(*FString::Printf(TEXT("lid_upper_%s"), Sides[s])));
		LidLowerIdx[s] = Bone(FName(*FString::Printf(TEXT("lid_lower_%s"), Sides[s])));
	}
	LidUpperFollow = Data.LidUpperFollow;
	LidLowerFollow = Data.LidLowerFollow;
	EyeMaxYaw = Data.EyeMaxYaw;
	EyeMaxUp = Data.EyeMaxPitchUp;
	EyeMaxDown = Data.EyeMaxPitchDown;
	MorphNames = Data.Morphs;
	DisabledMorphs = Data.DisabledMorphs;

	// ---- procedural helper rules
	Rules.Reset();
	for (const FMorphHelperRule& R : Data.HelperRules)
	{
		const int32 B = Bone(R.Bone), D = Bone(R.Driver);
		if (B != INDEX_NONE && D != INDEX_NONE)
		{
			Rules.Add({ B, D, (int32)R.Kind, R.Amount });
		}
	}
	Rules.Sort([](const FRule& A, const FRule& B) { return A.Bone < B.Bone; });

	// ---- secondary chain (ordered root -> tip)
	Chain.Reset();
	ChainLen.Reset();
	for (const FMorphBoneDef& Def : Data.Bones)
	{
		if (Data.SecondaryBones.Contains(Def.Name))
		{
			const int32 I = Bone(Def.Name);
			if (I != INDEX_NONE)
			{
				Chain.Add(I);
				ChainLen.Add(FMath::Max(Def.LengthCm, 0.5f));
			}
		}
	}
	bChainInit = false;

	// ---- aim poses (mesh-space rotations of every bone) and hit base poses (frame 0)
	AimCache.Reset();
	AimYaws.Reset();
	AimPitches.Reset();
	AimCenter = INDEX_NONE;
	HitBase.Reset();
	{
		FMemMark Mark(FMemStack::Get());
		TArray<FTransform> Local, CS;
		Local.SetNum(NumBones);
		for (const FOpAimPose& P : Cfg.AimPoses)
		{
			if (!P.Seq)
			{
				continue;
			}
			FCompactPose Pose;
			Pose.SetBoneContainer(&RB);
			FBlendedCurve Curve;
			Curve.InitFrom(RB);
			SampleSequence(P.Seq, 0.f, false, Pose, Curve);
			for (int32 i = 0; i < NumBones; ++i)
			{
				Local[i] = Pose[FCompactPoseBoneIndex(i)];
			}
			ComputeCS(Local, CS);
			FAimCache& AC = AimCache.AddDefaulted_GetRef();
			AC.Yaw = P.YawDeg;
			AC.Pitch = P.PitchDeg;
			AC.CSRot.SetNum(NumBones);
			AC.LocalTrans.SetNum(NumBones);
			for (int32 i = 0; i < NumBones; ++i)
			{
				AC.CSRot[i] = CS[i].GetRotation();
				AC.LocalTrans[i] = Local[i].GetTranslation();
			}
			AimYaws.AddUnique(P.YawDeg);
			AimPitches.AddUnique(P.PitchDeg);
			if (FMath::IsNearlyZero(P.YawDeg) && FMath::IsNearlyZero(P.PitchDeg))
			{
				AimCenter = AimCache.Num() - 1;
			}
		}
		AimYaws.Sort();
		AimPitches.Sort();
		for (const UAnimSequence* Seq : Cfg.HitClips)
		{
			if (!Seq)
			{
				continue;
			}
			FCompactPose Pose;
			Pose.SetBoneContainer(&RB);
			FBlendedCurve Curve;
			Curve.InitFrom(RB);
			SampleSequence(Seq, 0.f, false, Pose, Curve);
			TArray<FTransform>& Base = HitBase.Add(Seq);
			Base.SetNum(NumBones);
			for (int32 i = 0; i < NumBones; ++i)
			{
				Base[i] = Pose[FCompactPoseBoneIndex(i)];
			}
		}
	}

	L.SetNum(NumBones);
	C.SetNum(NumBones);
	U.SetNum(NumBones);
	RawBase.SetNum(NumBones);
	RawUpper.SetNum(NumBones);
	Inert.SetNum(NumBones);
	bHaveHistory = bHaveHistory2 = bHaveFrozen = false;
	bInertActive = false;
}

void FOperativeAnimProxy::ComputeCS(const TArray<FTransform>& Local, TArray<FTransform>& OutCS) const
{
	OutCS.SetNum(Local.Num(), EAllowShrinking::No);
	for (int32 i = 0; i < Local.Num(); ++i)
	{
		const int32 P = Parent[i];
		OutCS[i] = P >= 0 ? Local[i] * OutCS[P] : Local[i];
	}
}

void FOperativeAnimProxy::SetCSRotation(int32 BoneIndex, const FQuat& NewRot)
{
	const int32 P = Parent[BoneIndex];
	const FQuat ParentRot = P >= 0 ? C[P].GetRotation() : FQuat::Identity;
	L[BoneIndex].SetRotation((ParentRot.Inverse() * NewRot).GetNormalized());
	ComputeCS(L, C);
}

void FOperativeAnimProxy::SetCSTransform(int32 BoneIndex, const FTransform& NewCS)
{
	const int32 P = Parent[BoneIndex];
	L[BoneIndex] = P >= 0 ? NewCS.GetRelativeTransform(C[P]) : NewCS;
	L[BoneIndex].NormalizeRotation();
	ComputeCS(L, C);
}

void FOperativeAnimProxy::SampleBlend(const FBoneContainer& RB, TArrayView<const FOpClipSample> Samples, TArray<FTransform>& OutLocal, FBlendedCurve& OutCurve) const
{
	TArray<FCompactPose, TInlineAllocator<8>> Poses;
	TArray<FBlendedCurve, TInlineAllocator<8>> Curves;
	TArray<float, TInlineAllocator<8>> Weights;
	float Total = 0.f;
	for (const FOpClipSample& S : Samples)
	{
		if (S.Seq && S.Weight > 1.e-4f)
		{
			Total += S.Weight;
		}
	}
	OutLocal.SetNum(NumBones, EAllowShrinking::No);
	if (Total <= 0.f)
	{
		for (int32 i = 0; i < NumBones; ++i)
		{
			OutLocal[i] = RefLocal[i];
		}
		return;
	}
	Poses.Reserve(Samples.Num());
	Curves.Reserve(Samples.Num());
	for (const FOpClipSample& S : Samples)
	{
		if (!S.Seq || S.Weight <= 1.e-4f)
		{
			continue;
		}
		FCompactPose& P = Poses.AddDefaulted_GetRef();
		P.SetBoneContainer(&RB);
		FBlendedCurve& Cv = Curves.AddDefaulted_GetRef();
		Cv.InitFrom(RB);
		SampleSequence(S.Seq, S.Time, S.bLoop, P, Cv);
		Weights.Add(S.Weight / Total);
	}
	if (Poses.Num() == 1)
	{
		for (int32 i = 0; i < NumBones; ++i)
		{
			OutLocal[i] = Poses[0][FCompactPoseBoneIndex(i)];
		}
		OutCurve.CopyFrom(Curves[0]);
		return;
	}
	FCompactPose Result;
	Result.SetBoneContainer(&RB);
	FBlendedCurve ResultCurve;
	ResultCurve.InitFrom(RB);
	TArray<UE::Anim::FStackAttributeContainer, TInlineAllocator<8>> Attributes;
	Attributes.SetNum(Poses.Num());
	UE::Anim::FStackAttributeContainer ResultAttributes;
	FAnimationPoseData ResultData(Result, ResultCurve, ResultAttributes);
	FAnimationRuntime::BlendPosesTogether(Poses, Curves, Attributes, Weights, ResultData);
	for (int32 i = 0; i < NumBones; ++i)
	{
		OutLocal[i] = Result[FCompactPoseBoneIndex(i)];
	}
	OutCurve.CopyFrom(ResultCurve);
}

// ------------------------------------------------------------------------------------------------ evaluate
bool FOperativeAnimProxy::Evaluate(FPoseContext& Output)
{
	const FBoneContainer& RB = Output.Pose.GetBoneContainer();
	if (!RB.IsValid() || RB.GetCompactPoseNumBones() == 0)
	{
		return false;
	}
	EnsureCache(RB);

	// time dependent state advances once per game frame even if the pose is evaluated more often
	float StepDt = 0.f;
	if (In.FrameSerial != LastFrameSerial)
	{
		LastFrameSerial = In.FrameSerial;
		StepDt = FMath::Clamp(In.DeltaTime, 0.f, 0.1f);
	}

	if (In.bFrozen && bHaveFrozen && Frozen.Num() == NumBones)
	{
		for (int32 i = 0; i < NumBones; ++i)
		{
			Output.Pose[FCompactPoseBoneIndex(i)] = Frozen[i];
		}
		for (const TPair<FName, float>& KV : FrozenCurves)
		{
			Output.Curve.Set(KV.Key, KV.Value);
			Output.Curve.SetFlags(KV.Key, UE::Anim::ECurveElementFlags::MorphTarget);
		}
		return true;
	}

	FBlendedCurve Curve;
	Curve.InitFrom(RB);

	// 1 ---- base layer
	SampleBlend(RB, In.Base, L, Curve);
	RawBase = L;
	if (RootIdx != INDEX_NONE && !FMath::IsNearlyZero(In.RootYawOffsetDeg))
	{
		const FQuat Yaw(FVector::UpVector, FMath::DegreesToRadians(In.RootYawOffsetDeg));
		L[RootIdx].SetRotation((Yaw * L[RootIdx].GetRotation()).GetNormalized());
		L[RootIdx].SetTranslation(Yaw.RotateVector(L[RootIdx].GetTranslation()));
	}

	// wounded posture overlay
	if (In.OverlayAlpha > 1.e-3f && In.Overlay.Seq)
	{
		FBlendedCurve OverlayCurve;
		OverlayCurve.InitFrom(RB);
		const FOpClipSample One[1] = { In.Overlay };
		SampleBlend(RB, One, U, OverlayCurve);
		for (int32 i = 0; i < NumBones; ++i)
		{
			const float W = UpperWeight[i] * In.OverlayAlpha;
			if (W > 0.f)
			{
				L[i].BlendWith(U[i], W);
			}
		}
	}

	// 2 ---- upper-body action layer
	bool bHaveUpper = false;
	if (In.UpperAlpha > 1.e-3f && In.Upper.Num() > 0)
	{
		FBlendedCurve UpperCurve;
		UpperCurve.InitFrom(RB);
		SampleBlend(RB, In.Upper, U, UpperCurve);
		RawUpper = U;
		bHaveUpper = true;
		for (int32 i = 0; i < NumBones; ++i)
		{
			const float W = UpperWeight[i] * In.UpperAlpha;
			if (W >= 0.999f)
			{
				L[i] = U[i];
			}
			else if (W > 0.f)
			{
				L[i].BlendWith(U[i], W);
			}
		}
		Curve.UseMaxValue(UpperCurve);
	}

	// 3 ---- inertial blend out of the previous output whenever a source changed
	ApplyInertialization(StepDt);

	// 4 ---- additive hit reactions (local space)
	ApplyHits(RB);

	ComputeCS(L, C);

	// 5 ---- aim (mesh-space additive), look-at, ground adaptation
	ApplyAim();
	ApplyLookAt();
	ApplyFootIK();

	// 6 ---- face bones, procedural helpers, props, secondary chain
	ApplyFace();
	if (In.bProceduralBones)
	{
		ApplyProceduralBones();
	}
	if (In.PropAttach.Num() > 0)
	{
		// raw component-space pose of the clip that owns the prop track
		bool bNeedBase = false, bNeedUpper = false;
		for (const FOpPropAttach& A : In.PropAttach)
		{
			bNeedBase |= A.Source == 0;
			bNeedUpper |= A.Source == 1;
		}
		TArray<FTransform> RawBaseCS, RawUpperCS;
		if (bNeedBase)
		{
			ComputeCS(RawBase, RawBaseCS);
		}
		if (bNeedUpper && bHaveUpper)
		{
			ComputeCS(RawUpper, RawUpperCS);
		}
		for (const FOpPropAttach& A : In.PropAttach)
		{
			const int32 PropIdx = Bone(A.Prop), HolderIdx = Bone(A.Holder);
			const TArray<FTransform>& Raw = A.Source == 1 ? RawUpperCS : RawBaseCS;
			if (PropIdx == INDEX_NONE || HolderIdx == INDEX_NONE || Raw.Num() != NumBones || A.Weight <= 0.f)
			{
				continue;
			}
			const FTransform Rel = Raw[PropIdx].GetRelativeTransform(Raw[HolderIdx]);
			FTransform Target = Rel * C[HolderIdx];
			if (A.Weight < 0.999f)
			{
				FTransform Blend = C[PropIdx];
				Blend.BlendWith(Target, A.Weight);
				Target = Blend;
			}
			SetCSTransform(PropIdx, Target);
		}
	}
	for (const FName& Hidden : In.HiddenBones)
	{
		const int32 HiddenIdx = Bone(Hidden);
		if (HiddenIdx != INDEX_NONE)
		{
			L[HiddenIdx].SetScale3D(FVector(1.e-4));
		}
	}
	ApplySecondary(StepDt);

	// 7 ---- output
	for (int32 i = 0; i < NumBones; ++i)
	{
		L[i].NormalizeRotation();
		Output.Pose[FCompactPoseBoneIndex(i)] = L[i];
	}
	TMap<FName, float> Adds;
	for (const TPair<FName, float>& KV : In.MorphAdd)
	{
		Adds.FindOrAdd(KV.Key) += KV.Value;
	}
	FrozenCurves.Reset();
	for (const FName& Morph : MorphNames)
	{
		bool bHas = false;
		float V = Curve.Get(Morph, bHas, 0.f);
		const float* Add = Adds.Find(Morph);
		if (Add)
		{
			V += *Add;
		}
		if (bHas || Add)
		{
			V = DisabledMorphs.Contains(Morph) ? 0.f : FMath::Clamp(V, 0.f, 1.f);
			Curve.Set(Morph, V);
			Curve.SetFlags(Morph, UE::Anim::ECurveElementFlags::MorphTarget);
			if (V > 0.f)
			{
				FrozenCurves.Emplace(Morph, V);
			}
		}
	}
	Output.Curve.MoveFrom(Curve);
	if (StepDt > 0.f || !bHaveFrozen)
	{
		Frozen = L;
		bHaveFrozen = true;
	}
	return true;
}

// ------------------------------------------------------------------------------------------------ inertialization
void FOperativeAnimProxy::ApplyInertialization(float StepDt)
{
	if (In.TransitionSerial != LastTransitionSerial)
	{
		LastTransitionSerial = In.TransitionSerial;
		if (bHaveHistory && In.TransitionTime > 1.e-3f)
		{
			const float Dt = FMath::Max(PrevDt, 1.e-3f);
			for (int32 i = 0; i < NumBones; ++i)
			{
				FInertBone& IB = Inert[i];
				const FVector D = PrevOut[i].GetTranslation() - L[i].GetTranslation();
				IB.TransMag = (float)D.Size();
				IB.TransDir = IB.TransMag > 1.e-5f ? D / IB.TransMag : FVector::ZeroVector;
				IB.TransSpeed = 0.f;
				FQuat Q = PrevOut[i].GetRotation() * L[i].GetRotation().Inverse();
				Q.Normalize();
				if (Q.W < 0.0)
				{
					Q = Q * -1.0;
				}
				FVector Axis;
				double Angle = 0.0;
				Q.ToAxisAndAngle(Axis, Angle);
				IB.RotAxis = Axis.GetSafeNormal(1.e-8, FVector::UpVector);
				IB.RotAngle = (float)FMath::UnwindRadians(Angle);
				IB.RotSpeed = 0.f;
				if (bHaveHistory2)
				{
					const FVector DPrev = PrevPrevOut[i].GetTranslation() - L[i].GetTranslation();
					const float MagPrev = (float)FVector::DotProduct(DPrev, IB.TransDir);
					IB.TransSpeed = (IB.TransMag - MagPrev) / Dt;
					FQuat QP = PrevPrevOut[i].GetRotation() * L[i].GetRotation().Inverse();
					QP.Normalize();
					const double AnglePrev = FMath::UnwindRadians(2.0 * FMath::Atan2(FVector::DotProduct(FVector(QP.X, QP.Y, QP.Z), IB.RotAxis), QP.W));
					IB.RotSpeed = (float)FMath::UnwindRadians(IB.RotAngle - AnglePrev) / Dt;
				}
			}
			InertTime = 0.f;
			InertDuration = In.TransitionTime;
			bInertActive = true;
		}
	}
	else if (bInertActive)
	{
		InertTime += StepDt;
		if (InertTime >= InertDuration)
		{
			bInertActive = false;
		}
	}
	if (bInertActive)
	{
		for (int32 i = 0; i < NumBones; ++i)
		{
			const FInertBone& IB = Inert[i];
			if (IB.TransMag > 1.e-4f)
			{
				const float M = InertialFloat(IB.TransMag, IB.TransSpeed, InertTime, InertDuration);
				L[i].AddToTranslation(IB.TransDir * M);
			}
			if (IB.RotAngle > 1.e-5f)
			{
				const float A = InertialFloat(IB.RotAngle, IB.RotSpeed, InertTime, InertDuration);
				L[i].SetRotation((FQuat(IB.RotAxis, A) * L[i].GetRotation()).GetNormalized());
			}
		}
	}
	if (StepDt > 0.f || !bHaveHistory)
	{
		if (bHaveHistory)
		{
			PrevPrevOut = PrevOut;
			bHaveHistory2 = true;
		}
		PrevOut = L;
		bHaveHistory = true;
		if (StepDt > 0.f)
		{
			PrevDt = StepDt;
		}
	}
}

// ------------------------------------------------------------------------------------------------ hits
void FOperativeAnimProxy::ApplyHits(const FBoneContainer& RB)
{
	for (const FOpHitSample& H : In.Hits)
	{
		if (!H.Seq || H.Weight <= 1.e-3f)
		{
			continue;
		}
		const TArray<FTransform>* Base = HitBase.Find(H.Seq);
		if (!Base || Base->Num() != NumBones)
		{
			continue;
		}
		FCompactPose Pose;
		Pose.SetBoneContainer(&RB);
		FBlendedCurve Tmp;
		Tmp.InitFrom(RB);
		SampleSequence(H.Seq, H.Time, false, Pose, Tmp);
		for (int32 i = 0; i < NumBones; ++i)
		{
			const float W = HitWeight[i] * H.Weight;
			if (W <= 0.f)
			{
				continue;
			}
			const FTransform& Cur = Pose[FCompactPoseBoneIndex(i)];
			const FQuat Delta = (Cur.GetRotation() * (*Base)[i].GetRotation().Inverse()).GetNormalized();
			L[i].SetRotation((SlerpFromIdentity(Delta, W) * L[i].GetRotation()).GetNormalized());
			L[i].AddToTranslation((Cur.GetTranslation() - (*Base)[i].GetTranslation()) * W);
		}
	}
}

// ------------------------------------------------------------------------------------------------ aim
void FOperativeAnimProxy::ApplyAim()
{
	if (In.AimAlpha <= 1.e-3f || AimCenter == INDEX_NONE || AimYaws.Num() < 2 || AimPitches.Num() < 2)
	{
		return;
	}
	const float Yaw = FMath::Clamp(In.AimYawDeg, AimYaws[0], AimYaws.Last());
	const float Pitch = FMath::Clamp(In.AimPitchDeg, AimPitches[0], AimPitches.Last());
	int32 Y0 = 0, P0 = 0;
	while (Y0 < AimYaws.Num() - 2 && Yaw > AimYaws[Y0 + 1])
	{
		++Y0;
	}
	while (P0 < AimPitches.Num() - 2 && Pitch > AimPitches[P0 + 1])
	{
		++P0;
	}
	const float FY = (Yaw - AimYaws[Y0]) / FMath::Max(AimYaws[Y0 + 1] - AimYaws[Y0], 1.e-3f);
	const float FP = (Pitch - AimPitches[P0]) / FMath::Max(AimPitches[P0 + 1] - AimPitches[P0], 1.e-3f);
	auto Find = [&](float Yv, float Pv) -> const FAimCache*
	{
		for (const FAimCache& AC : AimCache)
		{
			if (FMath::IsNearlyEqual(AC.Yaw, Yv, 0.01f) && FMath::IsNearlyEqual(AC.Pitch, Pv, 0.01f))
			{
				return &AC;
			}
		}
		return nullptr;
	};
	const FAimCache* Corner[4] = { Find(AimYaws[Y0], AimPitches[P0]), Find(AimYaws[Y0 + 1], AimPitches[P0]),
		Find(AimYaws[Y0], AimPitches[P0 + 1]), Find(AimYaws[Y0 + 1], AimPitches[P0 + 1]) };
	const float W[4] = { (1 - FY) * (1 - FP), FY * (1 - FP), (1 - FY) * FP, FY * FP };
	const FAimCache& Center = AimCache[AimCenter];
	if (!Corner[0] || !Corner[1] || !Corner[2] || !Corner[3])
	{
		return;
	}
	// mesh-rotation-space additive: every masked bone gets delta = aim * inverse(center) applied to its mesh-space rotation
	TArray<FQuat, TInlineAllocator<128>> NewRot;
	NewRot.SetNum(NumBones);
	for (int32 i = 0; i < NumBones; ++i)
	{
		NewRot[i] = C[i].GetRotation();
		if (!AimMask[i])
		{
			continue;
		}
		const FQuat CenterInv = Center.CSRot[i].Inverse();
		FQuat Sum(0, 0, 0, 0);
		FVector TransDelta = FVector::ZeroVector;
		for (int32 k = 0; k < 4; ++k)
		{
			FQuat D = (Corner[k]->CSRot[i] * CenterInv).GetNormalized();
			if (D.W < 0.0)
			{
				D = D * -1.0;
			}
			Sum = Sum + D * (double)W[k];
			TransDelta += (Corner[k]->LocalTrans[i] - Center.LocalTrans[i]) * W[k];
		}
		Sum.Normalize();
		const FQuat Delta = SlerpFromIdentity(Sum, In.AimAlpha);
		NewRot[i] = (Delta * C[i].GetRotation()).GetNormalized();
		const int32 P = Parent[i];
		const FQuat ParentRot = P >= 0 ? NewRot[P] : FQuat::Identity;
		L[i].SetRotation((ParentRot.Inverse() * NewRot[i]).GetNormalized());
		L[i].AddToTranslation(TransDelta * In.AimAlpha);
	}
	ComputeCS(L, C);
}

// ------------------------------------------------------------------------------------------------ look-at
static FVector ClampDirection(const FVector& Dir, const FVector& Fwd, const FVector& Up, float MaxYawDeg, float MaxUpDeg, float MaxDownDeg)
{
	const FVector Right = FVector::CrossProduct(Up, Fwd).GetSafeNormal();
	const FVector Up2 = FVector::CrossProduct(Fwd, Right).GetSafeNormal();
	const double X = FVector::DotProduct(Dir, Fwd);
	const double Y = FVector::DotProduct(Dir, Right);
	const double Z = FVector::DotProduct(Dir, Up2);
	double Yaw = FMath::RadiansToDegrees(FMath::Atan2(Y, X));
	double Pitch = FMath::RadiansToDegrees(FMath::Atan2(Z, FMath::Sqrt(X * X + Y * Y)));
	Yaw = FMath::Clamp(Yaw, -(double)MaxYawDeg, (double)MaxYawDeg);
	Pitch = FMath::Clamp(Pitch, -(double)MaxDownDeg, (double)MaxUpDeg);
	const double CY = FMath::Cos(FMath::DegreesToRadians(Yaw)), SY = FMath::Sin(FMath::DegreesToRadians(Yaw));
	const double CP = FMath::Cos(FMath::DegreesToRadians(Pitch)), SP = FMath::Sin(FMath::DegreesToRadians(Pitch));
	return (Fwd * (CY * CP) + Right * (SY * CP) + Up2 * SP).GetSafeNormal();
}

void FOperativeAnimProxy::ApplyLookAt()
{
	if (HeadIdx == INDEX_NONE)
	{
		return;
	}
	const FVector Target = In.LookTargetCS;
	if (In.LookAlpha > 1.e-3f && ChestIdx != INDEX_NONE)
	{
		// reference directions carried by the chest
		const FQuat ChestDelta = C[ChestIdx].GetRotation() * RefCS[ChestIdx].GetRotation().Inverse();
		const FVector ChestFwd = ChestDelta.RotateVector(CS_FORWARD);
		const FVector ChestUp = ChestDelta.RotateVector(CS_UP);
		const FVector HeadFwdLocal = RefCS[HeadIdx].GetRotation().UnrotateVector(CS_FORWARD);
		FVector Dir = (Target - C[HeadIdx].GetLocation()).GetSafeNormal();
		if (!Dir.IsNearlyZero())
		{
			Dir = ClampDirection(Dir, ChestFwd, ChestUp, 70.f, 40.f, 35.f);
			if (NeckIdx != INDEX_NONE)
			{
				const FVector Cur = C[HeadIdx].GetRotation().RotateVector(HeadFwdLocal);
				const FQuat Q = SlerpFromIdentity(FQuat::FindBetweenNormals(Cur, Dir), 0.4f * In.LookAlpha);
				SetCSRotation(NeckIdx, Q * C[NeckIdx].GetRotation());
			}
			const FVector Cur = C[HeadIdx].GetRotation().RotateVector(HeadFwdLocal);
			const FQuat Q = SlerpFromIdentity(FQuat::FindBetweenNormals(Cur, Dir), In.LookAlpha);
			SetCSRotation(HeadIdx, Q * C[HeadIdx].GetRotation());
		}
	}
	if (In.EyeLookAlpha > 1.e-3f)
	{
		const FQuat HeadDelta = C[HeadIdx].GetRotation() * RefCS[HeadIdx].GetRotation().Inverse();
		const FVector HeadFwd = HeadDelta.RotateVector(CS_FORWARD);
		const FVector HeadUp = HeadDelta.RotateVector(CS_UP);
		for (int32 s = 0; s < 2; ++s)
		{
			const int32 EI = EyeIdx[s];
			if (EI == INDEX_NONE)
			{
				continue;
			}
			const FVector EyeFwdLocal = RefCS[EI].GetRotation().UnrotateVector(CS_FORWARD);
			FVector Dir = (Target - C[EI].GetLocation()).GetSafeNormal();
			if (Dir.IsNearlyZero())
			{
				continue;
			}
			Dir = ClampDirection(Dir, HeadFwd, HeadUp, EyeMaxYaw, EyeMaxUp, EyeMaxDown);
			const FQuat Before = L[EI].GetRotation();
			const FVector Cur = C[EI].GetRotation().RotateVector(EyeFwdLocal);
			const FQuat Q = SlerpFromIdentity(FQuat::FindBetweenNormals(Cur, Dir), In.EyeLookAlpha);
			SetCSRotation(EI, Q * C[EI].GetRotation());
			// eyelids follow the procedural part of the eye pitch (rotation about the shared local X axis)
			const FQuat LocalDelta = (Before.Inverse() * L[EI].GetRotation()).GetNormalized();
			const float PitchRad = (float)(2.0 * FMath::Atan2(LocalDelta.X, LocalDelta.W));
			const float Unwound = FMath::UnwindRadians(PitchRad);
			if (LidUpperIdx[s] != INDEX_NONE)
			{
				L[LidUpperIdx[s]].SetRotation((L[LidUpperIdx[s]].GetRotation() * FQuat(FVector(1, 0, 0), Unwound * LidUpperFollow)).GetNormalized());
			}
			if (LidLowerIdx[s] != INDEX_NONE)
			{
				L[LidLowerIdx[s]].SetRotation((L[LidLowerIdx[s]].GetRotation() * FQuat(FVector(1, 0, 0), Unwound * LidLowerFollow)).GetNormalized());
			}
		}
		ComputeCS(L, C);
	}
}

// ------------------------------------------------------------------------------------------------ ground adaptation
void FOperativeAnimProxy::ApplyFootIK()
{
	if (In.FootIKAlpha <= 1.e-3f || PelvisIdx == INDEX_NONE)
	{
		return;
	}
	const bool bFlat = FMath::Abs(In.FootOffsetZ[0]) < 0.05f && FMath::Abs(In.FootOffsetZ[1]) < 0.05f && FMath::Abs(In.PelvisOffsetZ) < 0.05f
		&& In.FootNormalCS[0].Z > 0.9995 && In.FootNormalCS[1].Z > 0.9995;
	if (bFlat)
	{
		return;
	}
	FVector FootTarget[2];
	FQuat FootRot[2];
	bool bValid[2] = { false, false };
	for (int32 s = 0; s < 2; ++s)
	{
		const FLeg& Leg = Legs[s];
		if (Leg.Thigh == INDEX_NONE || Leg.Calf == INDEX_NONE || Leg.Foot == INDEX_NONE)
		{
			continue;
		}
		bValid[s] = true;
		FootTarget[s] = C[Leg.Foot].GetLocation() + FVector(0, 0, In.FootOffsetZ[s] * In.FootIKAlpha);
		FQuat Align = FQuat::FindBetweenNormals(FVector::UpVector, In.FootNormalCS[s].GetSafeNormal(1.e-6, FVector::UpVector));
		Align = SlerpFromIdentity(Align, In.FootIKAlpha);
		FootRot[s] = (Align * C[Leg.Foot].GetRotation()).GetNormalized();
	}
	// pelvis drop
	if (!FMath::IsNearlyZero(In.PelvisOffsetZ))
	{
		FTransform P = C[PelvisIdx];
		P.AddToTranslation(FVector(0, 0, In.PelvisOffsetZ * In.FootIKAlpha));
		SetCSTransform(PelvisIdx, P);
	}
	for (int32 s = 0; s < 2; ++s)
	{
		if (!bValid[s])
		{
			continue;
		}
		const FLeg& Leg = Legs[s];
		const FVector RootPos = C[Leg.Thigh].GetLocation();
		const FVector JointPos = C[Leg.Calf].GetLocation();
		const FVector EndPos = C[Leg.Foot].GetLocation();
		// keep the authored knee direction as pole
		const FVector Axis = (EndPos - RootPos).GetSafeNormal();
		FVector Bend = (JointPos - RootPos) - Axis * FVector::DotProduct(JointPos - RootPos, Axis);
		if (Bend.SizeSquared() < 0.01)
		{
			Bend = C[Leg.Thigh].GetRotation().RotateVector(RefCS[Leg.Thigh].GetRotation().UnrotateVector(CS_FORWARD));
		}
		const FVector JointTarget = JointPos + Bend.GetSafeNormal() * 100.0;
		FVector OutJoint, OutEnd;
		AnimationCore::SolveTwoBoneIK(RootPos, JointPos, EndPos, JointTarget, FootTarget[s], OutJoint, OutEnd, false, 1.0, 1.0);
		const FQuat ThighDelta = FQuat::FindBetweenVectors(JointPos - RootPos, OutJoint - RootPos);
		SetCSRotation(Leg.Thigh, ThighDelta * C[Leg.Thigh].GetRotation());
		const FQuat CalfDelta = FQuat::FindBetweenVectors(C[Leg.Foot].GetLocation() - C[Leg.Calf].GetLocation(), OutEnd - C[Leg.Calf].GetLocation());
		SetCSRotation(Leg.Calf, CalfDelta * C[Leg.Calf].GetRotation());
		SetCSRotation(Leg.Foot, FootRot[s]);
	}
}

// ------------------------------------------------------------------------------------------------ face bones
void FOperativeAnimProxy::ApplyFace()
{
	if (In.FaceBones.Num() == 0)
	{
		return;
	}
	for (const FOpFaceBone& F : In.FaceBones)
	{
		const int32 BI = Bone(F.Bone);
		if (BI == INDEX_NONE || FMath::IsNearlyZero(F.Value))
		{
			continue;
		}
		// final(control) = clamp01(clip + layer) also holds for bone-driven controls: the amount the playing clips (and the
		// eyelid follow) already contribute along this control is measured on the bone, and only the remainder up to the
		// control's full offset is added. A baked blink plus an automatic one can therefore never over-rotate a lid.
		if (F.bRotation)
		{
			FQuat Offset = F.Quat;
			if (Offset.W < 0.0)
			{
				Offset = FQuat(-Offset.X, -Offset.Y, -Offset.Z, -Offset.W);
			}
			FVector Axis;
			double Angle = 0.0;
			Offset.ToAxisAndAngle(Axis, Angle);
			float Value = F.Value;
			if (Angle > 1.e-3)
			{
				const FQuat Current = (RefLocal[BI].GetRotation().Inverse() * L[BI].GetRotation()).GetNormalized();
				const float Existing = FMath::Clamp((float)(Current.GetTwistAngle(Axis) / Angle), 0.f, 1.f);
				Value = FMath::Min(Value, 1.f - Existing);
			}
			if (Value > 1.e-4f)
			{
				L[BI].SetRotation((L[BI].GetRotation() * SlerpFromIdentity(Offset, Value)).GetNormalized());
			}
		}
		else
		{
			const FVector Full = RefLocal[BI].GetRotation().RotateVector(F.Loc);
			float Value = F.Value;
			const double Len2 = Full.SizeSquared();
			if (Len2 > 1.e-6)
			{
				const float Existing = FMath::Clamp((float)(FVector::DotProduct(L[BI].GetTranslation() - RefLocal[BI].GetTranslation(), Full) / Len2), 0.f, 1.f);
				Value = FMath::Min(Value, 1.f - Existing);
			}
			if (Value > 1.e-4f)
			{
				L[BI].AddToTranslation(Full * Value);
			}
		}
	}
	ComputeCS(L, C);
}

// ------------------------------------------------------------------------------------------------ twist / half-rotation helpers
void FOperativeAnimProxy::ApplyProceduralBones()
{
	for (const FRule& R : Rules)
	{
		const FQuat Basis = (RefLocal[R.Driver].GetRotation().Inverse() * L[R.Driver].GetRotation()).GetNormalized();
		FQuat Result;
		if (R.Kind == FMorphHelperRule::Half)
		{
			Result = SlerpFromIdentity(Basis, R.Amount);
		}
		else
		{
			FQuat Swing, Twist;
			Basis.ToSwingTwist(BONE_AXIS, Swing, Twist);
			Result = SlerpFromIdentity(R.Kind == FMorphHelperRule::Untwist ? Twist.Inverse() : Twist, R.Amount);
		}
		L[R.Bone].SetRotation((RefLocal[R.Bone].GetRotation() * Result).GetNormalized());
	}
	ComputeCS(L, C);
}

// ------------------------------------------------------------------------------------------------ cable chain
void FOperativeAnimProxy::ApplySecondary(float StepDt)
{
	const int32 K = Chain.Num();
	if (K == 0)
	{
		return;
	}
	const FTransform& C2W = GetComponentTransform();
	TArray<FVector, TInlineAllocator<8>> A;
	A.SetNum(K + 1);
	for (int32 j = 0; j < K; ++j)
	{
		A[j] = C2W.TransformPosition(C[Chain[j]].GetLocation());
	}
	A[K] = C2W.TransformPosition(C[Chain[K - 1]].TransformPosition(FVector(0, -ChainLen[K - 1], 0)));
	const float Scale = (float)C2W.GetScale3D().Z;
	bool bReset = In.bResetSecondary || !bChainInit || ChainPos.Num() != K + 1 || !In.bSimulateSecondary;
	if (!bReset)
	{
		for (int32 j = 0; j <= K; ++j)
		{
			if (ChainPos[j].ContainsNaN() || FVector::DistSquared(ChainPos[j], A[j]) > FMath::Square(150.0))
			{
				bReset = true;
				break;
			}
		}
	}
	if (bReset)
	{
		ChainPos.SetNum(K + 1);
		ChainPrev.SetNum(K + 1);
		for (int32 j = 0; j <= K; ++j)
		{
			ChainPos[j] = ChainPrev[j] = A[j];
		}
		bChainInit = true;
		if (!In.bSimulateSecondary)
		{
			return;
		}
	}
	if (StepDt > 0.f)
	{
		const int32 Steps = FMath::Clamp(FMath::CeilToInt(StepDt * 90.f), 1, 8);
		const float H = StepDt / Steps;
		const float Retain = FMath::Pow(0.86f, H * 60.f);
		const float Stiff = 1.f - FMath::Exp(-14.f * H);
		const FVector Gravity(0, 0, -980.0 * 0.55);
		for (int32 Step = 0; Step < Steps; ++Step)
		{
			ChainPos[0] = A[0];
			ChainPrev[0] = A[0];
			for (int32 j = 1; j <= K; ++j)
			{
				const FVector Vel = (ChainPos[j] - ChainPrev[j]) * Retain;
				ChainPrev[j] = ChainPos[j];
				FVector P = ChainPos[j] + Vel + Gravity * (H * H);
				P += (A[j] - P) * Stiff;
				const float Len = ChainLen[j - 1] * Scale;
				FVector Dir = (P - ChainPos[j - 1]).GetSafeNormal(1.e-8, FVector(0, 0, -1));
				// cone limit around the animated direction keeps the cable out of the body and prevents runaway
				const FVector AnimDir = (A[j] - A[j - 1]).GetSafeNormal(1.e-8, FVector(0, 0, -1));
				const float MaxAngle = FMath::DegreesToRadians(32.f + 9.f * j);
				const float Angle = FMath::Acos(FMath::Clamp((float)FVector::DotProduct(Dir, AnimDir), -1.f, 1.f));
				if (Angle > MaxAngle)
				{
					const FQuat Q = FQuat::FindBetweenNormals(AnimDir, Dir);
					Dir = SlerpFromIdentity(Q, MaxAngle / Angle).RotateVector(AnimDir);
				}
				ChainPos[j] = ChainPos[j - 1] + Dir * Len;
			}
		}
	}
	// rotate every chain bone from its animated direction onto the simulated one
	for (int32 j = 0; j < K; ++j)
	{
		const int32 BI = Chain[j];
		const FVector Head = C[BI].GetLocation();
		const FVector Tip = j + 1 < K ? C[Chain[j + 1]].GetLocation() : C[BI].TransformPosition(FVector(0, -ChainLen[j], 0));
		const FVector CurDir = (Tip - Head).GetSafeNormal();
		const FVector SimDir = C2W.InverseTransformVectorNoScale(ChainPos[j + 1] - ChainPos[j]).GetSafeNormal();
		if (CurDir.IsNearlyZero() || SimDir.IsNearlyZero())
		{
			continue;
		}
		SetCSRotation(BI, FQuat::FindBetweenNormals(CurDir, SimDir) * C[BI].GetRotation());
	}
}
