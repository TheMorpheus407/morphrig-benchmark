// MORPHRIG: shared enums and plain data structs of the Operative runtime (manifest, events, pose recipe, face state).
#pragma once

#include "CoreMinimal.h"
#include "UObject/ObjectMacros.h"
#include "OperativeTypes.generated.h"

class UAnimSequence;

DECLARE_LOG_CATEGORY_EXTERN(LogMorphRig, Log, All);

constexpr int32 OPERATIVE_MAX_MORPHS = 64;
constexpr int32 OPERATIVE_MAX_VISEMES = 16;

/** Idle stance (selected by health and combat state). */
UENUM(BlueprintType)
enum class EOperativeStance : uint8
{
	Relaxed,
	Combat,
	Wounded
};

/** Top level state of the action component. The priority of every state is documented in docs/animation_state_contract.md. */
UENUM(BlueprintType)
enum class EOperativeState : uint8
{
	Locomotion,   // idle, start, move, stop, turn, pivot (grounded, free)
	Airborne,     // jump start/air, fall, land
	Dash,         // root motion dash (capsule driven by the clip)
	Blink,        // blink_out, teleport event, blink_in
	Action,       // committed full body action (melee, reload, casts, channel, charge, deploy, uplink, emotes, dialogue)
	Stun,
	Sleep,
	Knockback,
	Knockup,
	Knockdown,    // knockdown, prone, getup
	Dying,        // death clip playing
	Dead,         // dead pose held
	Respawning,
	Viewer        // animation browser playback of an arbitrary clip
};

UENUM(BlueprintType)
enum class EOperativeGait : uint8
{
	Walk,
	Run,
	Sprint
};

UENUM(BlueprintType)
enum class EOperativeFacingMode : uint8
{
	Aim,       // body turns towards the aim direction (top-down twin stick)
	Movement,  // body turns towards the movement direction
	Locked     // facing is held (inspection)
};

UENUM(BlueprintType)
enum class EOperativeAction : uint8
{
	None,
	Melee,
	Reload,
	CastGround,
	CastSelf,
	Channel,
	Charge,
	Deploy,
	Uplink,
	Greet,
	Victory,
	Defeat,
	Dialogue
};

UENUM(BlueprintType)
enum class EOperativeUpper : uint8
{
	None,
	RangedFire,
	RangedBurst,
	CastDirectional
};

/** Why an action ended early. */
UENUM(BlueprintType)
enum class EOperativeInterrupt : uint8
{
	Manual,     // player pressed the interrupt input
	Damage,     // non disabling damage
	Silence,
	Disable,    // stun, sleep, knock*: no interrupt clip, the disable state takes over
	Death,
	Cancel      // cancelled by a dash, blink or other cancel window action
};

/** One marker of a clip (from docs/animation_manifest.json). */
struct FOperativeEventDef
{
	FName Name;
	int32 Frame = 0;
	float TimeS = 0.f;
	TMap<FName, FString> Params;
	bool bSynthetic = false;   // created by the runtime fallback table because the manifest clip has no such event

	FString ParamString() const
	{
		FString Out;
		for (const TPair<FName, FString>& P : Params)
		{
			if (!Out.IsEmpty()) Out += TEXT(",");
			Out += P.Key.ToString() + TEXT("=") + P.Value;
		}
		return Out;
	}
};

struct FOperativeFootContact
{
	int32 Frame = 0;
	FName Foot;      // "l" or "r" (or as in the manifest)
	bool bPlant = true;
};

/** Manifest entry of one clip plus the resolved Unreal asset. */
struct FOperativeClipInfo
{
	FName Id;
	FString Form;                 // loop, one_shot, additive, pose
	FString Behavior;
	FName Layer;                  // full, upper, additive, pose
	bool bLoop = false;
	bool bStaticPose = false;
	bool bAdditive = false;
	bool bRootMotion = false;     // root_motion policy (dash)
	int32 Frames = 0;
	float DurationS = 0.f;
	float NominalSpeed = 0.f;     // cm/s
	FVector RootMotionCm = FVector::ZeroVector;
	TArray<FOperativeEventDef> Events;       // manifest events sorted by time
	TArray<FOperativeFootContact> FootContacts;
	TArray<FName> MorphCurves;
	TArray<FString> EntryStates;
	TArray<FString> ExitStates;
	TMap<FName, FString> Meta;             // procedural_components of the manifest (audio_offset_s, generator ...)
	UAnimSequence* Sequence = nullptr;   // kept alive by UOperativeAssets (hard references)

	float Length() const;         // play length of the sequence (falls back to the manifest duration)
	float StrideCm() const { return NominalSpeed * DurationS; }
};

/** One word or sentence of dialogue_alignment.json (subtitles and the word highlight). */
struct FOperativeSpeechSpan
{
	FString Text;
	float Start = 0.f;
	float End = 0.f;
	int32 Sentence = 0;
};

/** An event as it fires at runtime (hook argument, trace line and HUD entry). */
struct FOperativeEventInfo
{
	FName Name;
	FName ClipId;
	float ClipTime = 0.f;
	double WorldTime = 0.0;
	FString Params;
	bool bSynthetic = false;
	int32 PassId = 0;
	FName Player;                 // base, upper, hit
};

DECLARE_MULTICAST_DELEGATE_OneParam(FOperativeEventDelegate, const FOperativeEventInfo&);

/** A sampled sequence of the recipe. Sequence pointers are kept alive by the clip library. */
struct FOperativeSample
{
	const UAnimSequence* Seq = nullptr;
	float Time = 0.f;
	float Weight = 0.f;
	bool bLooping = false;
	bool bLockRootXY = true;      // in_place and root motion clips: horizontal root translation never moves the mesh
	bool bRootMotionClip = false; // the dash sequence has root motion enabled (extraction context)
};

/** Face state computed by UOperativeFaceComponent (code layer on top of the clip face). */
struct FOperativeFaceState
{
	float ClipFaceWeight = 1.f;                 // 1 = face bones and morph curves of the clip drive the face, 0 = ignore the clip face
	float CodeMorph[OPERATIVE_MAX_MORPHS] = {}; // additive morph weights of sliders, presets and visemes (0..1)
	int32 MorphCount = 0;
	float JawOpen = 0.f;                        // additive jaw opening 0..1 (24 degrees at 1)
	float TongueLift = 0.f;                     // 0..1
	float BlinkL = 0.f;                         // eyelid closure 0..1 (left = character left)
	float BlinkR = 0.f;
	float EyePitch = 0.f;                       // degrees, up positive
	float EyeYaw = 0.f;                         // degrees, left positive
	bool bEyesFromCode = true;                  // add EyePitch/EyeYaw to the animated eye bones
};

struct FOperativeFootIK
{
	bool bValid = false;
	float GroundOffset = 0.f;                   // ground height below the foot relative to the component origin (cm, smoothed)
	FVector Normal = FVector::UpVector;
};

/** Everything the anim proxy needs to build the pose of one frame. Built on the game thread by UOperativeActionComponent. */
struct FOperativePoseRecipe
{
	// Base layer (full body): weighted samples, weights sum to 1.
	TArray<FOperativeSample, TInlineAllocator<8>> Base;
	int32 SnapshotSerial = 0;                   // increments whenever the base source changes discontinuously
	float SnapshotAlpha = 0.f;                  // weight of the captured snapshot (1 at the change, fades to 0)

	// Upper body layer (spine_01 and up): ranged / cast clips
	FOperativeSample Upper;
	float UpperAlpha = 0.f;

	// Aim: aim ready pose over the upper body and additive offset from the nine aim poses
	float AimReadyAlpha = 0.f;
	float AimOffsetAlpha = 0.f;
	float AimYaw = 0.f;                         // degrees, left positive, -60..60
	float AimPitch = 0.f;                       // degrees, up positive, -35..35

	// Directional additive hit reactions (two slots)
	FOperativeSample Hit[2];
	float HitWeight[2] = {0.f, 0.f};

	// Look at, degrees relative to the body facing (left+, up+)
	float LookAlpha = 0.f;
	float HeadYaw = 0.f;
	float HeadPitch = 0.f;

	FOperativeFaceState Face;

	// Foot IK
	bool bFootIK = false;
	float FootIKAlpha = 0.f;
	float PelvisOffset = 0.f;
	FOperativeFootIK Foot[2];                   // 0 = left, 1 = right

	// Secondary motion (hair braid and cable chains)
	bool bSecondary = true;
	float SecondaryScale = 1.f;
	int32 SecondaryResetSerial = 0;
};

/** Runtime tunables shown in the docs and adjustable from the panel. */
namespace OperativeConst
{
	constexpr float WalkSpeed = 150.f;
	constexpr float RunSpeed = 400.f;
	constexpr float SprintSpeed = 650.f;
	constexpr float DashDistance = 200.f;
	constexpr float CapsuleRadius = 34.f;
	constexpr float CapsuleHalfHeight = 90.f;
	constexpr float StepHeight = 20.f;
}
