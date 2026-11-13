#include "MorphEventNotify.h"

FMorphEventNotifyDelegate UMorphEventNotify::OnEvent;

FString UMorphEventNotify::GetNotifyName_Implementation() const
{
	return EventName.IsNone() ? TEXT("MorphRig Event") : EventName.ToString();
}

void UMorphEventNotify::Notify(USkeletalMeshComponent* MeshComp, UAnimSequenceBase* Animation, const FAnimNotifyEventReference& EventReference)
{
	Super::Notify(MeshComp, Animation, EventReference);
	OnEvent.Broadcast(MeshComp, Animation, EventName);
}
