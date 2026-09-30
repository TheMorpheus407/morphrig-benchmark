// MORPHRIG: small static helpers that tools/ue_import_all.py calls because Python cannot set the name of a skeletal mesh socket.
#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "OperativeImportLibrary.generated.h"

class USkeletalMesh;

UCLASS()
class MORPHRIG_API UOperativeImportLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()
public:
	/** Adds (or replaces) a socket of the skeletal mesh; the transform is relative to the parent bone. */
	UFUNCTION(BlueprintCallable, Category = "Operative|Import")
	static bool AddOrReplaceSocket(USkeletalMesh* Mesh, FName SocketName, FName BoneName, const FTransform& RelativeTransform);

	UFUNCTION(BlueprintCallable, Category = "Operative|Import")
	static int32 CountMeshSockets(USkeletalMesh* Mesh);
};
