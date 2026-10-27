#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimNotifies/AnimNotify.h"
#include "MorphEventNotify.generated.h"

UCLASS(BlueprintType, EditInlineNew)
class MORPHRIG_API UMorphEventNotify : public UAnimNotify
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="MorphRig")
    FName EventName;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="MorphRig")
    FString EventType;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="MorphRig")
    float Value = 0.0f;

    virtual FString GetNotifyName_Implementation() const override
    {
        return EventName.IsNone() ? TEXT("MorphEvent") : EventName.ToString();
    }
};
