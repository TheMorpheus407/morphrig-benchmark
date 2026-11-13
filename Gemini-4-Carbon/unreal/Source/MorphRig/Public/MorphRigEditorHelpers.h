#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MorphRigEditorHelpers.generated.h"

class USkeletalMesh;
class UAnimSequence;

UCLASS()
class MORPHRIG_API UMorphRigEditorHelpers : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "MorphRig|Editor")
	static FString FinalizeOperativeAssets(
		USkeletalMesh* SkelMesh,
		UAnimSequence* IdleCombatSeq,
		const TArray<UAnimSequence*>& HitSeqs);
};
