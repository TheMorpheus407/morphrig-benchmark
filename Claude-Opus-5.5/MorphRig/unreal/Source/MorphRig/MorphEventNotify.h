#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimNotifies/AnimNotify.h"
#include "MorphEventNotify.generated.h"

/**
 * Named animation event authored in Blender as an action pose marker (hit windows, muzzle fire,
 * deploy attach/release, reload handoff, cast release, channel/charge transitions, foot contacts...).
 * The import script adds one notify per marker.  The showcase runtime reads them from the sequence
 * and dispatches them itself (exactly once per crossing, never on blend-out or after interruption);
 * the Notify() override therefore does nothing.
 */
UCLASS(meta = (DisplayName = "Morph Event"))
class MORPHRIG_API UMorphEventNotify : public UAnimNotify
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Morph")
	FName EventName;

	virtual FString GetNotifyName_Implementation() const override { return EventName.ToString(); }
};
