#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimNotifies/AnimNotify.h"
#include "MorphEventNotify.generated.h"

/**
 * Named marker placed on every imported sequence from animation_manifest.json.
 * The showcase controller dispatches markers itself (exactly-once rules of the state contract), so this notify
 * only carries the name; a game that plays the sequences through the stock animation system can still
 * listen to it through the multicast delegate below.
 */
DECLARE_MULTICAST_DELEGATE_ThreeParams(FMorphEventNotifyDelegate, USkeletalMeshComponent* /*Mesh*/, UAnimSequenceBase* /*Animation*/, FName /*Event*/);

UCLASS(meta = (DisplayName = "MorphRig Event"))
class MORPHRIG_API UMorphEventNotify : public UAnimNotify
{
	GENERATED_BODY()
public:
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "MorphRig")
	FName EventName;

	static FMorphEventNotifyDelegate OnEvent;

	virtual FString GetNotifyName_Implementation() const override;
	virtual void Notify(USkeletalMeshComponent* MeshComp, UAnimSequenceBase* Animation, const FAnimNotifyEventReference& EventReference) override;
};
