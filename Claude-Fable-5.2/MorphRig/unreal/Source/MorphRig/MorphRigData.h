// Runtime database read from Content/MorphRigData/*.json (copies of the delivery documents).
// Everything the controller knows about clips, markers, helper bones, sockets and face controls comes from here.
#pragma once
#include "CoreMinimal.h"

struct FMorphEvent
{
	FName Name;
	int32 Frame = 0;
	float Time = 0.f;
	float Normalized = 0.f;
};

/** A prop bone is carried by Holder between Start and End (seconds, clip local). */
struct FMorphPropSegment
{
	FName Prop;
	FName Holder;
	float Start = 0.f;
	float End = 0.f;
};

struct FMorphClip
{
	FName Id;
	FString Form;            // loop | one_shot | additive | pose
	FName Layer;             // base | locomotion | fullbody | upperbody | additive | aim
	FString AssetPath;
	bool bLoop = false;
	bool bPose = false;
	bool bRootMotion = false;
	int32 FrameEnd = 0;
	float Duration = 0.f;
	float NominalSpeed = 0.f;
	float TravelDirDeg = 0.f;
	FName Gait;
	float TurnYawDeg = 0.f;
	float AimYawDeg = 0.f;
	float AimPitchDeg = 0.f;
	float HitFromDeg = 0.f;
	FName FinalPose;
	FVector RootDisplacement = FVector::ZeroVector;
	TArray<FMorphEvent> Events;
	TArray<FMorphPropSegment> PropSegments;
	/** optional: travel speed per frame (cm/s, along the facing at clip start) of start / stop / pivot clips */
	TArray<float> SpeedProfile;
	/** optional: gait phase the clip is authored to start from / hands over to (-1 = not given) */
	float EntryPhase = -1.f;
	float ExitPhase = -1.f;
	/** the clip plants hands, knees or the body on the floor: no additive, aim, upper-body or IK layer may move it */
	bool bFloorContact = false;
	TArray<FString> EntryStates;
	TArray<FString> ExitStates;

	bool HasEvent(FName InName) const;
	/** Time of the first marker with that name, or Default when the clip has none. */
	float EventTime(FName InName, float Default) const;
};

struct FMorphBoneOffset
{
	FName Bone;
	bool bRotation = true;
	FQuat Quat = FQuat::Identity;      // Unreal bone-local rotation at control value 1
	FVector Loc = FVector::ZeroVector; // Unreal bone-local translation (cm) at control value 1
};

struct FMorphHelperRule
{
	enum EKind { Half, Untwist, Twist };
	FName Bone;
	FName Driver;
	EKind Kind = Half;
	float Amount = 0.5f;
};

struct FMorphSocketDef
{
	FName Name;
	FName Bone;
	FVector Position = FVector::ZeroVector; // Unreal component space rest position (cm)
	FVector Forward = FVector::ForwardVector;
	FVector Up = FVector::UpVector;
};

struct FMorphBoneDef
{
	FName Name;
	FName Parent;
	FString Role;
	float LengthCm = 0.f;
	FVector RefPositionCS = FVector::ZeroVector;
};

struct FMorphWord
{
	FString Text;
	FString Viseme;
	float Start = 0.f;
	float End = 0.f;
};

struct FMorphAlignment
{
	FString Text;
	float Duration = 0.f;
	float AudioStartTime = 0.f;
	TArray<FMorphWord> Words;
	TArray<FMorphWord> Phonemes;
};

class FMorphRigData
{
public:
	static const FMorphRigData& Get();
	static void Reload();

	bool bValid = false;
	bool bPlaceholder = false;
	FString Error;
	float Fps = 30.f;
	float WalkSpeed = 150.f;
	float RunSpeed = 400.f;
	float SprintSpeed = 650.f;

	TArray<FMorphClip> Clips;
	TMap<FName, int32> ClipIndex;

	TArray<FMorphBoneDef> Bones;
	TArray<FMorphHelperRule> HelperRules;
	TArray<FMorphSocketDef> Sockets;
	TArray<FName> PropBones;
	TArray<FName> SecondaryBones;

	// face
	TArray<FName> Morphs;
	/** Morph targets that failed the sanity check of the import (import_report.json); never driven at runtime. */
	TSet<FName> DisabledMorphs;
	TArray<FName> Controls;
	TMap<FName, TArray<FMorphBoneOffset>> BoneControls;
	TArray<FName> VisemeNames;
	TMap<FName, TMap<FName, float>> Visemes;
	TMap<FName, FString> VisemeNotes;
	TArray<FName> ExpressionNames;
	TMap<FName, TMap<FName, float>> Expressions;
	TArray<FName> EyeBones;
	float EyeMaxYaw = 32.f;
	float EyeMaxPitchUp = 22.f;
	float EyeMaxPitchDown = 28.f;
	float LidUpperFollow = 0.62f;
	float LidLowerFollow = 0.32f;

	FMorphAlignment Dialogue;

	const FMorphClip* Find(FName Id) const
	{
		const int32* I = ClipIndex.Find(Id);
		return I ? &Clips[*I] : nullptr;
	}

	/** bone and socket names the native controller refers to by name that are missing in skeleton_and_sockets.json */
	TArray<FString> MissingControllerNames() const;

	static FString DataDir();

private:
	void Load();
};
