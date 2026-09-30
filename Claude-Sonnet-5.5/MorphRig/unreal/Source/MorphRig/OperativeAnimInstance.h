// MORPHRIG: code only animation controller. The anim proxy skips the anim graph (Evaluate returns true) and builds the pose
// from an FOperativePoseRecipe that UOperativeActionComponent writes every frame: weighted base samples, pose snapshot blend,
// masked upper layer, aim ready pose plus additive aim offset, directional additive hits, face bones/curves, look at, foot IK
// and secondary motion (braid and cable chains).
#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "BonePose.h"
#include "OperativeTypes.h"
#include "OperativeAnimInstance.generated.h"

class UOperativeLibrary;

/** Values measured by the proxy during evaluation, read on the game thread after evaluation (debug, tests, HUD). */
struct FOperativeEvalDebug
{
	float AnkleHeightAnim[2] = {0.f, 0.f};   // animated ankle height above the component origin before IK
	float AnkleHeightFinal[2] = {0.f, 0.f};  // after IK
	float FootPlanted[2] = {0.f, 0.f};
	float PelvisZ = 0.f;
	FVector HandLeft = FVector::ZeroVector;  // component space
	FVector HandRight = FVector::ZeroVector;
	FVector FootLeft = FVector::ZeroVector;
	FVector FootRight = FVector::ZeroVector;
	FVector Head = FVector::ZeroVector;
	FVector Pelvis = FVector::ZeroVector;
	float SnapshotAlpha = 0.f;               // snapshot weight used in this evaluation
	float RecipeSnapshotAlpha = 0.f;         // snapshot weight requested by the controller
	int32 RecipeSerial = 0;                  // snapshot serial of the recipe
	int32 BoneMapRebuilds = 0;               // how often the bone container changed (LOD switch): the snapshot cannot span a rebuild
	float PelvisIKOffset = 0.f;
	int32 EvalCounter = 0;
	bool bValid = false;
};

/** Component space simulation state of one braid or cable chain. */
struct FOperativeChainSim
{
	TArray<FVector> P;      // joint positions (world space), P[0] pinned to the animated chain root
	TArray<FVector> Prev;
	bool bInit = false;
};

struct FOperativeBoneMap
{
	uint16 Serial = 0xFFFF;
	bool bValid = false;

	FCompactPoseBoneIndex Root, Pelvis, Spine01, Neck01, Neck02, Head, Jaw, Tongue[3];
	FCompactPoseBoneIndex Eye[2], LidUp[2], LidLo[2];
	FCompactPoseBoneIndex Thigh[2], Calf[2], Foot[2], Ball[2], Hand[2];
	FCompactPoseBoneIndex HairChain[5], CableChain[5];
	FCompactPoseBoneIndex ChainParent[2];    // head and lowerarm_l

	TArray<float> UpperMask;     // spine_01 and up (arms, hands, fingers, blade, props), excludes face, hair and cable bones
	TArray<float> FaceMask;      // jaw, tongue, eyes, lids
	TArray<FCompactPoseBoneIndex> FaceBones;

	// rest pose data for semantic rotations
	TArray<FQuat> RestCSRot;     // component space rest rotation per compact bone
	float RestAnkleZ[2] = {8.8f, 8.8f};
	FVector HairAlong[5];        // along axis (bone local) per chain bone
	float HairLen[5] = {5.f, 5.f, 5.f, 5.f, 5.f};
	FVector CableAlong[5];
	float CableLen[5] = {5.f, 5.f, 5.f, 5.f, 5.f};

	// cached aim data (local transforms per compact bone)
	bool bAimCached = false;
	TArray<FTransform> AimRefAbs;         // aim_level_center absolute pose
	TArray<FTransform> AimAdd[9];         // additive offsets relative to aim_level_center (index = pitch * 3 + yaw, 4 = center)
};

struct FOperativeAnimProxy : public FAnimInstanceProxy
{
	FOperativeAnimProxy() = default;
	explicit FOperativeAnimProxy(UAnimInstance* InInstance) : FAnimInstanceProxy(InInstance) {}

	virtual void Initialize(UAnimInstance* InAnimInstance) override;
	virtual void PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds) override;
	virtual void Update(float DeltaSeconds) override {}
	virtual bool Evaluate(FPoseContext& Output) override;
	virtual void PostEvaluate(UAnimInstance* InAnimInstance) override;

	// static data set once on the game thread (Initialize)
	const UAnimSequence* AimSeq[9] = {};
	TArray<FName> MorphNames;

	FOperativePoseRecipe Recipe;              // copy owned by the proxy, read on the evaluation thread

private:
	void EnsureBoneMap(const FBoneContainer& BC);
	void BuildBoneMap(const FBoneContainer& BC);
	void EnsureAimCache(const FBoneContainer& BC, FPoseContext& Scratch);
	void SampleInto(const FOperativeSample& S, FPoseContext& Ctx, bool bAdditive) const;
	void LerpAll(FCompactPose& A, const FCompactPose& B, float Alpha) const;
	void LerpMasked(FCompactPose& A, const FCompactPose& B, float Alpha, const TArray<float>& Mask) const;
	void ApplyFace(FCompactPose& Pose, const FBoneContainer& BC) const;
	void ApplyLook(FCompactPose& Pose, const FBoneContainer& BC) const;
	void ApplyFootIK(FCompactPose& Pose, const FBoneContainer& BC, float Dt);
	void ApplySecondary(FCompactPose& Pose, const FBoneContainer& BC, float Dt);
	FTransform ComponentSpaceOf(const FCompactPose& Pose, const FBoneContainer& BC, FCompactPoseBoneIndex Bone) const;
	void SimulateChain(FOperativeChainSim& Sim, FCompactPose& Pose, const FBoneContainer& BC, const FCompactPoseBoneIndex* Chain, const FVector* Along, const float* Len, FCompactPoseBoneIndex ChainParent, float Dt, float Scale, bool bReset, float Stiffness, float Damping, float Gravity);

	FOperativeBoneMap Map;
	// snapshot for interruption blending
	TArray<FTransform> LastBaseBones;
	TArray<float> LastBaseMorph;
	TArray<FTransform> SnapshotBones;
	TArray<float> SnapshotMorph;
	bool bLastBaseValid = false;
	bool bSnapshotValid = false;
	int32 AppliedSnapshotSerial = -1;
	int32 AppliedSecondaryReset = -1;
	uint16 LastBaseSerial = 0xFFFF;

	FOperativeChainSim HairSim;
	FOperativeChainSim CableSim;
	FVector LastComponentLocation = FVector::ZeroVector;
	bool bHaveLastComponent = false;

public:
	FOperativeEvalDebug Debug;
};

UCLASS(Transient)
class MORPHRIG_API UOperativeAnimInstance : public UAnimInstance
{
	GENERATED_BODY()
public:
	UOperativeAnimInstance();

	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
	virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override;
	virtual void NativeInitializeAnimation() override;
	virtual void NativeUpdateAnimation(float DeltaSeconds) override;
	virtual void NativePostEvaluateAnimation() override;

	/** Called by the action component (game thread) once per frame before the mesh ticks. */
	void SetRecipe(const FOperativePoseRecipe& InRecipe) { PendingRecipe = InRecipe; }
	const FOperativePoseRecipe& GetPendingRecipe() const { return PendingRecipe; }
	const FOperativeEvalDebug& GetEvalDebug() const { return EvalDebug; }

	FOperativePoseRecipe PendingRecipe;
	FOperativeEvalDebug EvalDebug;
};
