// MORPHRIG: notify created by tools/ue_import_all.py for every manifest event so the markers are visible in the animation editor.
// The runtime reads events from the manifest (one source of truth), these notifies are the editor side view of the same data.
#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimNotifies/AnimNotify.h"
#include "OperativeEventNotify.generated.h"

UCLASS(const, HideDropdown, meta = (DisplayName = "Operative Event"))
class MORPHRIG_API UOperativeEventNotify : public UAnimNotify
{
	GENERATED_BODY()
public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	FName EventName;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	FString Params;

	virtual FString GetNotifyName_Implementation() const override
	{
		return Params.IsEmpty() ? EventName.ToString() : FString::Printf(TEXT("%s (%s)"), *EventName.ToString(), *Params);
	}
};
