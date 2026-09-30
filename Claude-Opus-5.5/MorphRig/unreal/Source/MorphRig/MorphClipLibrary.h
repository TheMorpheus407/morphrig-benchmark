#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "MorphClipLibrary.generated.h"

class UAnimSequence;

/** Clip ids and marker names are lowercase snake_case; FName keeps the casing of the first registration of an
 *  equal name anywhere in the engine ("Dialogue", "Activate"), so display them through this helper. */
inline FString MorphIdStr(FName N) { return N.ToString().ToLower(); }

struct FMorphMarker
{
	float Time = 0.f;
	FName Name;
};

/** One animation entry of the showcase (inventory clip or an extra helper clip). */
struct FMorphClip
{
	FName Id;
	UAnimSequence* Seq = nullptr;
	float Duration = 0.f;
	int32 Frames = 0;
	bool bLoop = false;
	bool bAdditive = false;
	bool bRootMotion = false;
	bool bRequired = true;           // one of the 96 inventory entries
	FString Form;                    // loop / one_shot / additive / pose
	FString Root;                    // in_place / root_motion
	FString Layer;                   // full_body / upper_body / additive ...
	float SpeedCms = 0.f;
	FString Entry, Exit, Notes, Behavior;
	TArray<FMorphMarker> Markers;
};

/**
 * Loads the clip table (MorphRig/Data/clips.json, staged with the build) and the AnimSequence
 * assets it references.  Markers come from the sequences' UMorphEventNotify notifies.
 */
UCLASS()
class MORPHRIG_API UMorphClipLibrary : public UObject
{
	GENERATED_BODY()

public:
	bool Load();
	const FMorphClip* Find(FName Id) const;
	const TArray<FMorphClip>& All() const { return Clips; }
	int32 NumRequired() const;

private:
	TArray<FMorphClip> Clips;
	TMap<FName, int32> Index;

	UPROPERTY()
	TArray<TObjectPtr<UAnimSequence>> Loaded;
};
