#include "OperativeAnimInstance.h"
#include "OperativeLibrary.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimNodeBase.h"
#include "Animation/AnimationPoseData.h"
#include "AnimationRuntime.h"
#include "BoneContainer.h"
#include "TwoBoneIK.h"
#include "Components/SkeletalMeshComponent.h"
#include "HAL/IConsoleManager.h"

static TAutoConsoleVariable<int32> CVarNoMorph(TEXT("mr.NoMorph"), 0, TEXT("1 evaluates the operative without any morph curve (debug switch for shading investigations)."), ECVF_Default);

static TAutoConsoleVariable<int32> CVarRefPose(TEXT("mr.RefPose"), 0, TEXT("1 outputs the skeleton reference pose without animation (debug switch for skinning investigations)."), ECVF_Default);

namespace
{
	inline bool Valid(FCompactPoseBoneIndex I) { return I.GetInt() >= 0; }
	const FVector CsRight(0.f, 1.f, 0.f);   // component space: +X forward, +Y right, +Z up
	const FVector CsUp(0.f, 0.f, 1.f);

	// Face rig semantics in component space (right handed quaternion formula on Unreal axes):
	//   rotation about +Y by a positive angle tips a forward pointing bone downwards, about +Z it turns it to the right.
	//   jaw open / upper lid close = +Y, tongue lift / lower lid close / eye pitch up = -Y, eye yaw left = -Z.
	constexpr float JawOpenDeg = 24.f;
	constexpr float LidUpCloseDeg = 36.f;
	constexpr float LidLoCloseDeg = 15.f;
	constexpr float LidUpFollow = 0.45f;
	constexpr float LidLoFollow = 0.25f;
	constexpr float TongueLiftDeg[3] = { 12.f, 7.f, 5.f };
}

// ------------------------------------------------------------------------------------------------ anim instance

UOperativeAnimInstance::UOperativeAnimInstance()
{
	bUseMultiThreadedAnimationUpdate = false;
}

FAnimInstanceProxy* UOperativeAnimInstance::CreateAnimInstanceProxy()
{
	return new FOperativeAnimProxy(this);
}

void UOperativeAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy)
{
	delete static_cast<FOperativeAnimProxy*>(InProxy);
}

void UOperativeAnimInstance::NativeInitializeAnimation()
{
	Super::NativeInitializeAnimation();
	FOperativeAnimProxy& Proxy = GetProxyOnGameThread<FOperativeAnimProxy>();
	if (const UOperativeLibrary* Lib = UOperativeLibrary::Get(this))
	{
		static const TCHAR* Pitch[3] = { TEXT("down"), TEXT("level"), TEXT("up") };
		static const TCHAR* Yaw[3] = { TEXT("right"), TEXT("center"), TEXT("left") };
		for (int32 P = 0; P < 3; ++P)
		{
			for (int32 Y = 0; Y < 3; ++Y)
			{
				Proxy.AimSeq[P * 3 + Y] = Lib->GetSequence(FName(*FString::Printf(TEXT("aim_%s_%s"), Pitch[P], Yaw[Y])));
			}
		}
		Proxy.MorphNames = Lib->GetMorphNames();
	}
}

void UOperativeAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeUpdateAnimation(DeltaSeconds);
}

void UOperativeAnimInstance::NativePostEvaluateAnimation()
{
	Super::NativePostEvaluateAnimation();
}

// ------------------------------------------------------------------------------------------------ proxy: lifecycle

void FOperativeAnimProxy::Initialize(UAnimInstance* InAnimInstance)
{
	FAnimInstanceProxy::Initialize(InAnimInstance);
}

void FOperativeAnimProxy::PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds)
{
	FAnimInstanceProxy::PreUpdate(InAnimInstance, DeltaSeconds);
	if (const UOperativeAnimInstance* AI = Cast<UOperativeAnimInstance>(InAnimInstance))
	{
		Recipe = AI->PendingRecipe;
	}
}

void FOperativeAnimProxy::PostEvaluate(UAnimInstance* InAnimInstance)
{
	FAnimInstanceProxy::PostEvaluate(InAnimInstance);
	if (UOperativeAnimInstance* AI = Cast<UOperativeAnimInstance>(InAnimInstance))
	{
		AI->EvalDebug = Debug;
	}
}

// ------------------------------------------------------------------------------------------------ proxy: bone map

void FOperativeAnimProxy::EnsureBoneMap(const FBoneContainer& BC)
{
	if (Map.bValid && Map.Serial == BC.GetSerialNumber()) return;
	++Debug.BoneMapRebuilds;
	BuildBoneMap(BC);
}

void FOperativeAnimProxy::BuildBoneMap(const FBoneContainer& BC)
{
	Map = FOperativeBoneMap();
	Map.Serial = BC.GetSerialNumber();
	auto Find = [&](const TCHAR* Name) -> FCompactPoseBoneIndex
	{
		const int32 MeshIdx = BC.GetPoseBoneIndexForBoneName(FName(Name));
		if (MeshIdx == INDEX_NONE) return FCompactPoseBoneIndex(INDEX_NONE);
		return BC.MakeCompactPoseIndex(FMeshPoseBoneIndex(MeshIdx));
	};
	auto FindS = [&](const TCHAR* Base, int32 Side) { return Find(*FString::Printf(TEXT("%s_%s"), Base, Side == 0 ? TEXT("l") : TEXT("r"))); };
	Map.Root = Find(TEXT("root"));
	Map.Pelvis = Find(TEXT("pelvis"));
	Map.Spine01 = Find(TEXT("spine_01"));
	Map.Neck01 = Find(TEXT("neck_01"));
	Map.Neck02 = Find(TEXT("neck_02"));
	Map.Head = Find(TEXT("head"));
	Map.Jaw = Find(TEXT("jaw"));
	for (int32 I = 0; I < 3; ++I) Map.Tongue[I] = Find(*FString::Printf(TEXT("tongue_%02d"), I + 1));
	for (int32 S = 0; S < 2; ++S)
	{
		Map.Eye[S] = FindS(TEXT("eye"), S);
		Map.LidUp[S] = FindS(TEXT("lid_up"), S);
		Map.LidLo[S] = FindS(TEXT("lid_lo"), S);
		Map.Thigh[S] = FindS(TEXT("thigh"), S);
		Map.Calf[S] = FindS(TEXT("calf"), S);
		Map.Foot[S] = FindS(TEXT("foot"), S);
		Map.Ball[S] = FindS(TEXT("ball"), S);
		Map.Hand[S] = FindS(TEXT("hand"), S);
	}
	for (int32 I = 0; I < 5; ++I)
	{
		Map.HairChain[I] = Find(*FString::Printf(TEXT("hair_%02d"), I + 1));
		Map.CableChain[I] = Find(*FString::Printf(TEXT("cable_%02d"), I + 1));
	}
	Map.ChainParent[0] = Find(TEXT("head"));
	Map.ChainParent[1] = Find(TEXT("lowerarm_l"));

	const int32 N = BC.GetCompactPoseNumBones();
	if (N <= 0 || !Valid(Map.Root) || !Valid(Map.Pelvis)) return;

	// masks
	TArray<uint8> InUpper, Excluded;
	InUpper.Init(0, N);
	Excluded.Init(0, N);
	Map.UpperMask.Init(0.f, N);
	Map.FaceMask.Init(0.f, N);
	Map.RestCSRot.Init(FQuat::Identity, N);
	TArray<FTransform> RestCS;
	RestCS.Init(FTransform::Identity, N);
	auto IsExcludedRoot = [&](int32 I)
	{
		const FCompactPoseBoneIndex C(I);
		return C == Map.Jaw || C == Map.Eye[0] || C == Map.Eye[1] || C == Map.LidUp[0] || C == Map.LidUp[1] || C == Map.LidLo[0] || C == Map.LidLo[1]
			|| C == Map.HairChain[0] || C == Map.CableChain[0];
	};
	auto IsFaceRoot = [&](int32 I)
	{
		const FCompactPoseBoneIndex C(I);
		return C == Map.Jaw || C == Map.Eye[0] || C == Map.Eye[1] || C == Map.LidUp[0] || C == Map.LidUp[1] || C == Map.LidLo[0] || C == Map.LidLo[1];
	};
	TArray<uint8> InFace;
	InFace.Init(0, N);
	for (int32 I = 0; I < N; ++I)
	{
		const FCompactPoseBoneIndex C(I);
		const FCompactPoseBoneIndex P = BC.GetParentBoneIndex(C);
		const bool bHasParent = Valid(P);
		const FTransform& RefLocal = BC.GetRefPoseTransform(C);
		RestCS[I] = bHasParent ? RefLocal * RestCS[P.GetInt()] : RefLocal;
		Map.RestCSRot[I] = RestCS[I].GetRotation();
		InUpper[I] = (C == Map.Spine01) || (bHasParent && InUpper[P.GetInt()]);
		Excluded[I] = IsExcludedRoot(I) || (bHasParent && Excluded[P.GetInt()]);
		InFace[I] = IsFaceRoot(I) || (bHasParent && InFace[P.GetInt()]);
		if (InUpper[I] && !Excluded[I]) Map.UpperMask[I] = 1.f;
		if (InFace[I])
		{
			Map.FaceMask[I] = 1.f;
			Map.FaceBones.Add(C);
		}
	}
	if (Valid(Map.Root)) Map.UpperMask[0] = 0.f;
	{
		const FCompactPoseBoneIndex PC = Find(TEXT("prop_cell")), PB = Find(TEXT("prop_beacon"));
		if (Valid(PC)) Map.UpperMask[PC.GetInt()] = 1.f;
		if (Valid(PB)) Map.UpperMask[PB.GetInt()] = 1.f;
	}
	for (int32 S = 0; S < 2; ++S)
	{
		if (Valid(Map.Foot[S])) Map.RestAnkleZ[S] = RestCS[Map.Foot[S].GetInt()].GetLocation().Z;
	}
	// chain along axes (bone local) and lengths from the reference pose
	auto Chain = [&](const FCompactPoseBoneIndex* Bones, FVector* Along, float* Len)
	{
		for (int32 I = 0; I < 5; ++I)
		{
			if (!Valid(Bones[I])) return;
		}
		for (int32 I = 0; I < 4; ++I)
		{
			const FVector D = BC.GetRefPoseTransform(Bones[I + 1]).GetLocation();
			Len[I] = FMath::Max(D.Size(), 1.f);
			Along[I] = D.GetSafeNormal();
		}
		Len[4] = Len[3];
		Along[4] = Along[3];
	};
	Chain(Map.HairChain, Map.HairAlong, Map.HairLen);
	Chain(Map.CableChain, Map.CableAlong, Map.CableLen);
	Map.bValid = true;
}

void FOperativeAnimProxy::EnsureAimCache(const FBoneContainer& BC, FPoseContext& Scratch)
{
	if (Map.bAimCached || !Map.bValid) return;
	const UAnimSequence* Centre = AimSeq[4];
	if (!Centre) return;
	const int32 N = BC.GetCompactPoseNumBones();
	auto Extract = [&](const UAnimSequence* Seq, TArray<FTransform>& Out)
	{
		FOperativeSample S;
		S.Seq = Seq;
		S.Time = 0.f;
		SampleInto(S, Scratch, false);
		Out.SetNum(N);
		for (const FCompactPoseBoneIndex I : Scratch.Pose.ForEachBoneIndex()) Out[I.GetInt()] = Scratch.Pose[I];
	};
	Extract(Centre, Map.AimRefAbs);
	for (int32 K = 0; K < 9; ++K)
	{
		if (K == 4 || !AimSeq[K])
		{
			Map.AimAdd[K].Init(FTransform::Identity, N);
			// additive identity has zero scale delta
			for (FTransform& T : Map.AimAdd[K]) { T.SetTranslation(FVector::ZeroVector); T.SetRotation(FQuat::Identity); T.SetScale3D(FVector::ZeroVector); }
			continue;
		}
		Extract(AimSeq[K], Map.AimAdd[K]);
		for (int32 B = 0; B < N; ++B) FAnimationRuntime::ConvertTransformToAdditive(Map.AimAdd[K][B], Map.AimRefAbs[B]);
	}
	Map.bAimCached = true;
}

// ------------------------------------------------------------------------------------------------ proxy: pose helpers

void FOperativeAnimProxy::SampleInto(const FOperativeSample& S, FPoseContext& Ctx, bool bAdditive) const
{
	if (bAdditive) Ctx.ResetToAdditiveIdentity(); else Ctx.ResetToRefPose();
	if (!S.Seq) return;
	const double Len = S.Seq->GetPlayLength();
	const double T = FMath::Clamp((double)S.Time, 0.0, Len);
	FAnimExtractContext Extract(T, S.bRootMotionClip, FDeltaTimeRecord(), S.bLooping);
	FAnimationPoseData PD(Ctx);
	S.Seq->GetAnimationPose(PD, Extract);
	if (S.bLockRootXY && !bAdditive && Ctx.Pose.GetNumBones() > 0)
	{
		FTransform& R = Ctx.Pose[FCompactPoseBoneIndex(0)];
		FVector L = R.GetTranslation();
		L.X = 0.f;
		L.Y = 0.f;
		R.SetTranslation(L);
	}
}

void FOperativeAnimProxy::LerpAll(FCompactPose& A, const FCompactPose& B, float Alpha) const
{
	if (Alpha <= 1e-4f) return;
	if (Alpha >= 0.9999f)
	{
		A.CopyBonesFrom(B);
		return;
	}
	const ScalarRegister W1(1.f - Alpha), W2(Alpha);
	for (const FCompactPoseBoneIndex I : A.ForEachBoneIndex())
	{
		FTransform& T = A[I];
		T *= W1;
		T.AccumulateWithShortestRotation(B[I], W2);
		T.NormalizeRotation();
	}
}

void FOperativeAnimProxy::LerpMasked(FCompactPose& A, const FCompactPose& B, float Alpha, const TArray<float>& Mask) const
{
	if (Alpha <= 1e-4f) return;
	for (const FCompactPoseBoneIndex I : A.ForEachBoneIndex())
	{
		const float W = Alpha * Mask[I.GetInt()];
		if (W <= 1e-4f) continue;
		const ScalarRegister W1(1.f - W), W2(W);
		FTransform& T = A[I];
		T *= W1;
		T.AccumulateWithShortestRotation(B[I], W2);
		T.NormalizeRotation();
	}
}

FTransform FOperativeAnimProxy::ComponentSpaceOf(const FCompactPose& Pose, const FBoneContainer& BC, FCompactPoseBoneIndex Bone) const
{
	FTransform T = Pose[Bone];
	FCompactPoseBoneIndex P = BC.GetParentBoneIndex(Bone);
	while (Valid(P))
	{
		T = T * Pose[P];
		P = BC.GetParentBoneIndex(P);
	}
	return T;
}

// ------------------------------------------------------------------------------------------------ proxy: evaluation

bool FOperativeAnimProxy::Evaluate(FPoseContext& Output)
{
	const FBoneContainer& BC = Output.Pose.GetBoneContainer();
	EnsureBoneMap(BC);
	Output.ResetToRefPose();
	if (!Map.bValid || CVarRefPose.GetValueOnAnyThread() != 0) return true;

	const FOperativePoseRecipe& R = Recipe;
	const int32 NB = BC.GetCompactPoseNumBones();
	const int32 NM = FMath::Min(MorphNames.Num(), OPERATIVE_MAX_MORPHS);
	const float Dt = FMath::Clamp(GetDeltaSeconds(), 0.f, 0.05f);

	// ---- base layer: weighted samples
	float Morph[OPERATIVE_MAX_MORPHS] = {};
	{
		bool bFirst = true;
		float Acc = 0.f;
		for (const FOperativeSample& S : R.Base)
		{
			if (!S.Seq || S.Weight <= 1e-4f) continue;
			FPoseContext Tmp(Output);
			SampleInto(S, Tmp, false);
			for (int32 M = 0; M < NM; ++M)
			{
				bool bHas = false;
				const float V = Tmp.Curve.Get(MorphNames[M], bHas, 0.f);
				if (bHas) Morph[M] += S.Weight * V;
			}
			Acc += S.Weight;
			if (bFirst)
			{
				Output.Pose.CopyBonesFrom(Tmp.Pose);
				bFirst = false;
			}
			else
			{
				LerpAll(Output.Pose, Tmp.Pose, S.Weight / Acc);
			}
		}
		if (!bFirst && Acc > 1e-4f && FMath::Abs(Acc - 1.f) > 1e-3f)
		{
			for (int32 M = 0; M < NM; ++M) Morph[M] /= Acc;
		}
	}

	// ---- snapshot blend (pose captured at the last discontinuous change of the base source)
	if (R.SnapshotSerial != AppliedSnapshotSerial)
	{
		AppliedSnapshotSerial = R.SnapshotSerial;
		if (bLastBaseValid && LastBaseSerial == Map.Serial)
		{
			SnapshotBones = LastBaseBones;
			SnapshotMorph = LastBaseMorph;
			bSnapshotValid = true;
		}
		else
		{
			bSnapshotValid = false;
		}
	}
	if (bSnapshotValid && R.SnapshotAlpha > 1e-3f && SnapshotBones.Num() == NB)
	{
		const float A = FMath::Clamp(R.SnapshotAlpha, 0.f, 1.f);
		const ScalarRegister W1(1.f - A), W2(A);
		for (const FCompactPoseBoneIndex I : Output.Pose.ForEachBoneIndex())
		{
			FTransform& T = Output.Pose[I];
			T *= W1;
			T.AccumulateWithShortestRotation(SnapshotBones[I.GetInt()], W2);
			T.NormalizeRotation();
		}
		for (int32 M = 0; M < NM && M < SnapshotMorph.Num(); ++M) Morph[M] = FMath::Lerp(Morph[M], SnapshotMorph[M], A);
	}

	// remember the displayed base for the next snapshot
	LastBaseBones.SetNum(NB);
	for (const FCompactPoseBoneIndex I : Output.Pose.ForEachBoneIndex()) LastBaseBones[I.GetInt()] = Output.Pose[I];
	LastBaseMorph.SetNum(NM);
	for (int32 M = 0; M < NM; ++M) LastBaseMorph[M] = Morph[M];
	bLastBaseValid = true;
	LastBaseSerial = Map.Serial;

	// ---- aim ready pose over the upper body, then the upper body clip
	{
		FPoseContext Tmp(Output);
		EnsureAimCache(BC, Tmp);
	}
	if (R.AimReadyAlpha > 1e-3f && Map.bAimCached && Map.AimRefAbs.Num() == NB)
	{
		for (const FCompactPoseBoneIndex I : Output.Pose.ForEachBoneIndex())
		{
			const float W = R.AimReadyAlpha * Map.UpperMask[I.GetInt()];
			if (W <= 1e-4f) continue;
			FTransform& T = Output.Pose[I];
			T *= ScalarRegister(1.f - W);
			T.AccumulateWithShortestRotation(Map.AimRefAbs[I.GetInt()], ScalarRegister(W));
			T.NormalizeRotation();
		}
	}
	if (R.Upper.Seq && R.UpperAlpha > 1e-3f)
	{
		FPoseContext Tmp(Output);
		SampleInto(R.Upper, Tmp, false);
		LerpMasked(Output.Pose, Tmp.Pose, R.UpperAlpha, Map.UpperMask);
	}

	// ---- aim offset: bilinear blend of the eight additive aim poses
	if (R.AimOffsetAlpha > 1e-3f && Map.bAimCached)
	{
		const float Yaw = FMath::Clamp(R.AimYaw, -60.f, 60.f);
		const float Pitch = FMath::Clamp(R.AimPitch, -35.f, 35.f);
		const float FY = (Yaw + 60.f) / 60.f;      // 0..2 across right, centre, left
		const float FP = (Pitch + 35.f) / 35.f;    // 0..2 across down, level, up
		const int32 IY = FMath::Min((int32)FY, 1), IP = FMath::Min((int32)FP, 1);
		const float TY = FY - IY, TP = FP - IP;
		const float WY[2] = { 1.f - TY, TY };
		const float WP[2] = { 1.f - TP, TP };
		for (int32 DP = 0; DP < 2; ++DP)
		{
			for (int32 DY = 0; DY < 2; ++DY)
			{
				const float W = WY[DY] * WP[DP] * R.AimOffsetAlpha;
				const int32 K = (IP + DP) * 3 + (IY + DY);
				if (W <= 1e-4f || K == 4 || Map.AimAdd[K].Num() != NB) continue;
				for (const FCompactPoseBoneIndex I : Output.Pose.ForEachBoneIndex())
				{
					const float BW = W * Map.UpperMask[I.GetInt()];
					if (BW <= 1e-4f) continue;
					FTransform::BlendFromIdentityAndAccumulate(Output.Pose[I], Map.AimAdd[K][I.GetInt()], ScalarRegister(BW));
				}
			}
		}
	}

	// ---- directional additive hits
	for (int32 H = 0; H < 2; ++H)
	{
		if (!R.Hit[H].Seq || R.HitWeight[H] <= 1e-3f) continue;
		FPoseContext Add(Output, true);
		if (R.Hit[H].Seq->IsValidAdditive())
		{
			SampleInto(R.Hit[H], Add, true);
		}
		else
		{
			// fallback: additive relative to frame 0 of the same sequence
			FPoseContext Base0(Output);
			FOperativeSample S0 = R.Hit[H];
			S0.Time = 0.f;
			SampleInto(R.Hit[H], Add, false);
			SampleInto(S0, Base0, false);
			FAnimationRuntime::ConvertPoseToAdditive(Add.Pose, Base0.Pose);
		}
		for (const FCompactPoseBoneIndex I : Output.Pose.ForEachBoneIndex())
		{
			const float BW = R.HitWeight[H] * Map.UpperMask[I.GetInt()];
			if (BW <= 1e-4f) continue;
			FTransform::BlendFromIdentityAndAccumulate(Output.Pose[I], Add.Pose[I], ScalarRegister(BW));
		}
	}
	Output.Pose.NormalizeRotations();

	// ---- face, look at, foot IK, secondary motion
	ApplyFace(Output.Pose, BC);
	ApplyLook(Output.Pose, BC);
	ApplyFootIK(Output.Pose, BC, Dt);
	if (R.bSecondary) ApplySecondary(Output.Pose, BC, Dt);
	Output.Pose.NormalizeRotations();

	// ---- morph curves: clip curves (base) plus code layer
	{
		Output.Curve.Empty();
		const FOperativeFaceState& F = R.Face;
		for (int32 M = 0; M < NM; ++M)
		{
			const float V = FMath::Clamp(Morph[M] * F.ClipFaceWeight + (M < OPERATIVE_MAX_MORPHS ? F.CodeMorph[M] : 0.f), 0.f, 1.f);
			if (V > 1e-4f && CVarNoMorph.GetValueOnAnyThread() == 0) Output.Curve.Set(MorphNames[M], V);
		}
	}

	// ---- debug data for tests and the HUD
	{
		auto Pos = [&](FCompactPoseBoneIndex B) { return Valid(B) ? ComponentSpaceOf(Output.Pose, BC, B).GetLocation() : FVector::ZeroVector; };
		Debug.HandLeft = Pos(Map.Hand[0]);
		Debug.HandRight = Pos(Map.Hand[1]);
		Debug.FootLeft = Pos(Map.Foot[0]);
		Debug.FootRight = Pos(Map.Foot[1]);
		Debug.Head = Pos(Map.Head);
		Debug.Pelvis = Pos(Map.Pelvis);
		Debug.AnkleHeightFinal[0] = Debug.FootLeft.Z;
		Debug.AnkleHeightFinal[1] = Debug.FootRight.Z;
		Debug.PelvisZ = Debug.Pelvis.Z;
		Debug.SnapshotAlpha = (bSnapshotValid ? R.SnapshotAlpha : 0.f);
		Debug.RecipeSnapshotAlpha = R.SnapshotAlpha;
		Debug.RecipeSerial = R.SnapshotSerial;
		Debug.PelvisIKOffset = R.PelvisOffset * R.FootIKAlpha;
		++Debug.EvalCounter;
		Debug.bValid = true;
	}
	return true;
}

// ------------------------------------------------------------------------------------------------ proxy: face

void FOperativeAnimProxy::ApplyFace(FCompactPose& Pose, const FBoneContainer& BC) const
{
	const FOperativeFaceState& F = Recipe.Face;
	if (F.ClipFaceWeight < 0.999f)
	{
		for (const FCompactPoseBoneIndex B : Map.FaceBones)
		{
			FTransform& T = Pose[B];
			T.BlendWith(BC.GetRefPoseTransform(B), 1.f - F.ClipFaceWeight);
		}
	}
	// rotation defined in the frame of the parent bone (rest orientation), axis given in component space
	auto Rot = [&](FCompactPoseBoneIndex B, const FVector& CsAxis, float AngleDeg)
	{
		if (!Valid(B) || FMath::Abs(AngleDeg) < 1e-3f) return;
		const FCompactPoseBoneIndex P = BC.GetParentBoneIndex(B);
		const FQuat PR = Valid(P) ? Map.RestCSRot[P.GetInt()] : FQuat::Identity;
		const FVector AxisP = PR.UnrotateVector(CsAxis);
		const FQuat D(AxisP, FMath::DegreesToRadians(AngleDeg));
		FTransform& T = Pose[B];
		T.SetRotation((D * T.GetRotation()).GetNormalized());
	};
	Rot(Map.Jaw, CsRight, JawOpenDeg * F.JawOpen);
	for (int32 I = 0; I < 3; ++I) Rot(Map.Tongue[I], CsRight, -TongueLiftDeg[I] * F.TongueLift);
	for (int32 S = 0; S < 2; ++S)
	{
		if (F.bEyesFromCode)
		{
			Rot(Map.Eye[S], CsRight, -F.EyePitch);
			Rot(Map.Eye[S], CsUp, -F.EyeYaw);
		}
		const float Blink = S == 0 ? F.BlinkL : F.BlinkR;
		Rot(Map.LidUp[S], CsRight, LidUpCloseDeg * Blink - LidUpFollow * F.EyePitch);
		Rot(Map.LidLo[S], CsRight, -(LidLoCloseDeg * Blink + LidLoFollow * F.EyePitch));
	}
}

// ------------------------------------------------------------------------------------------------ proxy: look at

void FOperativeAnimProxy::ApplyLook(FCompactPose& Pose, const FBoneContainer& BC) const
{
	const FOperativePoseRecipe& R = Recipe;
	const float A = FMath::Clamp(R.LookAlpha, 0.f, 1.f);
	if (A < 1e-3f) return;
	const float Yaw = FMath::Clamp(R.HeadYaw, -75.f, 75.f) * A;
	const float Pitch = FMath::Clamp(R.HeadPitch, -40.f, 40.f) * A;
	if (FMath::Abs(Yaw) < 0.01f && FMath::Abs(Pitch) < 0.01f) return;
	const FQuat DTotal = FQuat(CsUp, -FMath::DegreesToRadians(Yaw)) * FQuat(CsRight, -FMath::DegreesToRadians(Pitch));
	const FCompactPoseBoneIndex Bones[3] = { Map.Neck01, Map.Neck02, Map.Head };
	const float Weights[3] = { 0.20f, 0.30f, 0.50f };
	for (int32 I = 0; I < 3; ++I)
	{
		if (!Valid(Bones[I])) continue;
		const FCompactPoseBoneIndex P = BC.GetParentBoneIndex(Bones[I]);
		const FQuat PR = Valid(P) ? ComponentSpaceOf(Pose, BC, P).GetRotation() : FQuat::Identity;
		const FQuat D = FQuat::Slerp(FQuat::Identity, DTotal, Weights[I]);
		FTransform& T = Pose[Bones[I]];
		T.SetRotation((PR.Inverse() * D * PR * T.GetRotation()).GetNormalized());
	}
}

// ------------------------------------------------------------------------------------------------ proxy: foot IK

void FOperativeAnimProxy::ApplyFootIK(FCompactPose& Pose, const FBoneContainer& BC, float Dt)
{
	const FOperativePoseRecipe& R = Recipe;
	for (int32 S = 0; S < 2; ++S)
	{
		Debug.FootPlanted[S] = 0.f;
		Debug.AnkleHeightAnim[S] = Valid(Map.Foot[S]) ? ComponentSpaceOf(Pose, BC, Map.Foot[S]).GetLocation().Z : 0.f;
	}
	if (!R.bFootIK || R.FootIKAlpha < 0.01f || !Valid(Map.Pelvis)) return;
	const float Alpha = FMath::Clamp(R.FootIKAlpha, 0.f, 1.f);
	const float Dz = R.PelvisOffset * Alpha;
	Pose[Map.Pelvis].AddToTranslation(FVector(0.f, 0.f, Dz));
	for (int32 S = 0; S < 2; ++S)
	{
		const FCompactPoseBoneIndex Thigh = Map.Thigh[S], Calf = Map.Calf[S], Foot = Map.Foot[S];
		if (!Valid(Thigh) || !Valid(Calf) || !Valid(Foot)) continue;
		const FTransform PelvisCS = ComponentSpaceOf(Pose, BC, Map.Pelvis);
		FTransform ThighCS = Pose[Thigh] * PelvisCS;
		FTransform CalfCS = Pose[Calf] * ThighCS;
		FTransform FootCS = Pose[Foot] * CalfCS;
		const float AnimZ = FootCS.GetLocation().Z - Dz;
		const float Height = AnimZ - Map.RestAnkleZ[S];
		const float Planted = 1.f - FMath::Clamp((Height - 1.5f) / 7.f, 0.f, 1.f);
		Debug.FootPlanted[S] = Planted;
		const float G = R.Foot[S].bValid ? R.Foot[S].GroundOffset : 0.f;
		float TargetZ = AnimZ + G * Planted * Alpha;
		TargetZ = FMath::Max(TargetZ, G * Alpha + Map.RestAnkleZ[S] * 0.85f);
		const FVector FootLoc = FootCS.GetLocation();
		if (FMath::Abs(TargetZ - FootLoc.Z) < 0.02f && Planted < 0.01f) continue;
		const FVector Effector(FootLoc.X, FootLoc.Y, TargetZ);
		const FVector JointTarget = CalfCS.GetLocation() + FVector(60.f, 0.f, 0.f);
		FTransform U = ThighCS, L = CalfCS, E = FootCS;
		AnimationCore::SolveTwoBoneIK(U, L, E, JointTarget, Effector, false, 1.0, 1.0);
		FQuat FootRot = FootCS.GetRotation();
		if (R.Foot[S].bValid)
		{
			FQuat Align = FQuat::FindBetweenNormals(FVector::UpVector, R.Foot[S].Normal.GetSafeNormal());
			FVector Axis;
			float Angle;
			Align.ToAxisAndAngle(Axis, Angle);
			const float MaxTilt = FMath::DegreesToRadians(25.f);
			if (Angle > MaxTilt) Align = FQuat(Axis, MaxTilt);
			FootRot = FQuat::Slerp(FootRot, Align * FootRot, Planted * Alpha).GetNormalized();
		}
		E.SetRotation(FootRot);
		Pose[Thigh] = U.GetRelativeTransform(PelvisCS);
		Pose[Calf] = L.GetRelativeTransform(U);
		Pose[Foot] = E.GetRelativeTransform(L);
		Debug.AnkleHeightFinal[S] = E.GetLocation().Z;
	}
}

// ------------------------------------------------------------------------------------------------ proxy: secondary motion

void FOperativeAnimProxy::ApplySecondary(FCompactPose& Pose, const FBoneContainer& BC, float Dt)
{
	const FOperativePoseRecipe& R = Recipe;
	const bool bReset = (R.SecondaryResetSerial != AppliedSecondaryReset);
	AppliedSecondaryReset = R.SecondaryResetSerial;
	const float Scale = FMath::Clamp(R.SecondaryScale, 0.f, 1.f);
	SimulateChain(HairSim, Pose, BC, Map.HairChain, Map.HairAlong, Map.HairLen, Map.ChainParent[0], Dt, Scale, bReset, 0.10f, 0.94f, 0.9f);
	SimulateChain(CableSim, Pose, BC, Map.CableChain, Map.CableAlong, Map.CableLen, Map.ChainParent[1], Dt, Scale, bReset, 0.14f, 0.92f, 0.7f);
}

void FOperativeAnimProxy::SimulateChain(FOperativeChainSim& Sim, FCompactPose& Pose, const FBoneContainer& BC, const FCompactPoseBoneIndex* Chain, const FVector* Along, const float* Len, FCompactPoseBoneIndex ChainParent, float Dt, float Scale, bool bReset, float Stiffness, float Damping, float GravityScale)
{
	constexpr int32 N = 5;
	for (int32 I = 0; I < N; ++I)
	{
		if (!Valid(Chain[I])) return;
	}
	if (!Valid(ChainParent)) return;
	const FTransform& CompToWorld = GetComponentTransform();

	const FTransform ParentCS = ComponentSpaceOf(Pose, BC, ChainParent);
	FTransform AnimCS[N];
	FTransform Par = ParentCS;
	for (int32 I = 0; I < N; ++I)
	{
		AnimCS[I] = Pose[Chain[I]] * Par;
		Par = AnimCS[I];
	}
	FVector A[N + 1];
	for (int32 I = 0; I < N; ++I) A[I] = CompToWorld.TransformPosition(AnimCS[I].GetLocation());
	A[N] = CompToWorld.TransformPosition(AnimCS[N - 1].TransformPosition(Along[N - 1] * Len[N - 1]));

	if (!Sim.bInit || bReset || Sim.P.Num() != N + 1 || FVector::DistSquared(Sim.P[0], A[0]) > FMath::Square(150.f))
	{
		Sim.P.SetNum(N + 1);
		Sim.Prev.SetNum(N + 1);
		for (int32 I = 0; I <= N; ++I) { Sim.P[I] = A[I]; Sim.Prev[I] = A[I]; }
		Sim.bInit = true;
	}
	if (Dt > 1e-5f)
	{
		const int32 Steps = FMath::Clamp(FMath::CeilToInt(Dt * 90.f), 1, 4);
		const float H = Dt / Steps;
		const float Damp = FMath::Pow(Damping, H * 90.f);
		const float Stiff = FMath::Min(Stiffness * H * 90.f, 0.5f);
		for (int32 Step = 0; Step < Steps; ++Step)
		{
			const FVector Pin = A[0];
			Sim.Prev[0] = Sim.P[0];
			Sim.P[0] = Pin;
			for (int32 J = 1; J <= N; ++J)
			{
				const FVector Vel = (Sim.P[J] - Sim.Prev[J]) * Damp;
				Sim.Prev[J] = Sim.P[J];
				Sim.P[J] += Vel + FVector(0.f, 0.f, -980.f) * GravityScale * H * H;
				Sim.P[J] += (A[J] - Sim.P[J]) * Stiff;
			}
			for (int32 Iter = 0; Iter < 3; ++Iter)
			{
				Sim.P[0] = Pin;
				for (int32 J = 1; J <= N; ++J)
				{
					FVector D = Sim.P[J] - Sim.P[J - 1];
					const float DL = D.Size();
					if (DL > 1e-4f) Sim.P[J] = Sim.P[J - 1] + D * (Len[J - 1] / DL);
				}
			}
		}
	}
	// pose the chain bones towards the simulated joints (bounded to 50 degrees from the animated direction)
	FVector Ps[N + 1];
	for (int32 I = 0; I <= N; ++I) Ps[I] = CompToWorld.InverseTransformPosition(FMath::Lerp(A[I], Sim.P[I], Scale));
	FTransform ParCS = ParentCS;
	const float MaxAngle = FMath::DegreesToRadians(50.f);
	for (int32 I = 0; I < N; ++I)
	{
		const FTransform Cur = Pose[Chain[I]] * ParCS;
		const FVector CurDir = Cur.GetRotation().RotateVector(Along[I]);
		const FVector DesDir = (Ps[I + 1] - Ps[I]).GetSafeNormal();
		FQuat Delta = DesDir.IsNearlyZero() ? FQuat::Identity : FQuat::FindBetweenNormals(CurDir, DesDir);
		FVector Axis;
		float Angle;
		Delta.ToAxisAndAngle(Axis, Angle);
		if (Angle > MaxAngle) Delta = FQuat(Axis, MaxAngle);
		const FTransform NewCS(FQuat((Delta * Cur.GetRotation()).GetNormalized()), Cur.GetLocation(), Cur.GetScale3D());
		Pose[Chain[I]] = NewCS.GetRelativeTransform(ParCS);
		ParCS = NewCS;
	}
}
