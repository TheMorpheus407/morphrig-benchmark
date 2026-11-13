#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "OperativeAnimTypes.h"
#include "OperativeAnimInstance.generated.h"

class UAnimSequence;

/**
 * Native animation controller of the Operative. There is no AnimGraph: FOperativeAnimProxy::Evaluate builds the
 * pose in C++ from the FOperativeAnimInput snapshot written by UOperativeStateComponent every tick
 * (layers 1-8 of docs/animation_state_contract.md).
 */
UCLASS(Transient, NotBlueprintable)
class MORPHRIG_API UOperativeAnimInstance : public UAnimInstance
{
	GENERATED_BODY()
public:
	UOperativeAnimInstance();

	virtual void NativeInitializeAnimation() override;

	UAnimSequence* GetSequence(FName Id) const;
	int32 NumLoadedSequences() const { return Sequences.Num(); }

	/** Written on the game thread, copied to the worker in PreUpdate. */
	FOperativeAnimInput Input;
	FOperativeAnimConfig Config;

protected:
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
	virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override;

	UPROPERTY(Transient)
	TMap<FName, TObjectPtr<UAnimSequence>> Sequences;
};

struct FOperativeAnimProxy : public FAnimInstanceProxy
{
	FOperativeAnimProxy() = default;
	explicit FOperativeAnimProxy(UAnimInstance* InInstance) : FAnimInstanceProxy(InInstance) {}

	virtual void PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds) override;
	virtual bool Evaluate(FPoseContext& Output) override;

private:
	struct FInertBone
	{
		FVector TransDir = FVector::ZeroVector;
		float TransMag = 0.f;
		float TransSpeed = 0.f;
		FVector RotAxis = FVector::UpVector;
		float RotAngle = 0.f;
		float RotSpeed = 0.f;
	};
	struct FAimCache
	{
		float Yaw = 0.f;
		float Pitch = 0.f;
		TArray<FQuat> CSRot;
		TArray<FVector> LocalTrans;
	};
	struct FLeg
	{
		int32 Thigh = INDEX_NONE, Calf = INDEX_NONE, Foot = INDEX_NONE;
	};

	void EnsureCache(const FBoneContainer& RB);
	int32 Bone(FName Name) const { const int32* I = BoneMap.Find(Name); return I ? *I : INDEX_NONE; }
	void SampleBlend(const FBoneContainer& RB, TArrayView<const FOpClipSample> Samples, TArray<FTransform>& OutLocal, FBlendedCurve& OutCurve) const;
	void ComputeCS(const TArray<FTransform>& Local, TArray<FTransform>& OutCS) const;
	void SetCSRotation(int32 BoneIndex, const FQuat& NewRot);
	void SetCSTransform(int32 BoneIndex, const FTransform& NewCS);
	void ApplyInertialization(float StepDt);
	void ApplyHits(const FBoneContainer& RB);
	void ApplyAim();
	void ApplyLookAt();
	void ApplyFootIK();
	void ApplyFace();
	void ApplyProceduralBones();
	void ApplySecondary(float StepDt);

	FOperativeAnimInput In;
	FOperativeAnimConfig Cfg;

	// ---- caches (rebuilt when the required bone set changes)
	uint16 CachedSerial = 0xFFFF;
	uint32 CachedConfigSerial = 0xFFFFFFFF;
	int32 NumBones = 0;
	TMap<FName, int32> BoneMap;
	TArray<int32> Parent;
	TArray<FTransform> RefLocal;
	TArray<FTransform> RefCS;
	TArray<float> UpperWeight;
	TArray<float> HitWeight;
	TArray<uint8> AimMask;
	TArray<FAimCache> AimCache;
	TArray<float> AimYaws;
	TArray<float> AimPitches;
	int32 AimCenter = INDEX_NONE;
	TMap<const UAnimSequence*, TArray<FTransform>> HitBase;
	struct FRule { int32 Bone; int32 Driver; int32 Kind; float Amount; };
	TArray<FRule> Rules;
	FLeg Legs[2];
	int32 PelvisIdx = INDEX_NONE, RootIdx = INDEX_NONE, HeadIdx = INDEX_NONE, NeckIdx = INDEX_NONE, ChestIdx = INDEX_NONE;
	int32 EyeIdx[2] = { INDEX_NONE, INDEX_NONE };
	int32 LidUpperIdx[2] = { INDEX_NONE, INDEX_NONE };
	int32 LidLowerIdx[2] = { INDEX_NONE, INDEX_NONE };
	TArray<int32> Chain;
	TArray<float> ChainLen;
	float LidUpperFollow = 0.6f, LidLowerFollow = 0.3f, EyeMaxYaw = 32.f, EyeMaxUp = 22.f, EyeMaxDown = 28.f;
	TArray<FName> MorphNames;
	TSet<FName> DisabledMorphs;

	// ---- working state
	TArray<FTransform> L, C, U, RawBase, RawUpper, RawCS;
	TArray<FTransform> PrevOut, PrevPrevOut, Frozen;
	bool bHaveHistory = false, bHaveHistory2 = false, bHaveFrozen = false;
	float PrevDt = 1.f / 30.f;
	TArray<FInertBone> Inert;
	float InertTime = 0.f, InertDuration = 0.f;
	bool bInertActive = false;
	uint32 LastTransitionSerial = 0;
	uint32 LastFrameSerial = 0xFFFFFFFF;
	TArray<FVector> ChainPos, ChainPrev;
	bool bChainInit = false;
	TArray<TPair<FName, float>> FrozenCurves;
};
