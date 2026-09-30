// MORPHRIG: content registry (data asset created by the import script) and the world subsystem that parses the manifest.
#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "Subsystems/WorldSubsystem.h"
#include "OperativeTypes.h"
#include "OperativeLibrary.generated.h"

class USkeletalMesh;
class UStaticMesh;
class USoundBase;
class UMaterialInterface;
class USkeleton;

/** Written by tools/ue_import_all.py: references to every imported asset plus the manifest JSON text. */
UCLASS(BlueprintType)
class MORPHRIG_API UOperativeAssets : public UDataAsset
{
	GENERATED_BODY()
public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	TObjectPtr<USkeletalMesh> Mesh;

	/** All AnimSequences, named exactly like the manifest clip ids. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	TArray<TObjectPtr<UAnimSequence>> Clips;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	TObjectPtr<UStaticMesh> PowerCellMesh;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	TObjectPtr<UStaticMesh> BeaconMesh;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	TObjectPtr<USoundBase> DialogueSound;

	/** Engine basic shapes referenced with hard references so they are cooked (showcase room, effects). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	TObjectPtr<UStaticMesh> CubeMesh;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	TObjectPtr<UStaticMesh> SphereMesh;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	TObjectPtr<UStaticMesh> CylinderMesh;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	TObjectPtr<UStaticMesh> PlaneMesh;

	/** Slot names of the mesh materials (MI_skin ...); TeamAMaterials/TeamBMaterials are parallel arrays. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	TArray<FName> MaterialSlotNames;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	TArray<TObjectPtr<UMaterialInterface>> TeamAMaterials;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	TArray<TObjectPtr<UMaterialInterface>> TeamBMaterials;

	/** Secondary outline (overlay material, inverted hull): index 0 = team A, 1 = team B. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	TArray<TObjectPtr<UMaterialInterface>> OutlineMaterials;

	/** Named helper materials: Normal, Clay, Wireframe, Fx, Floor, Target, Prop. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	TMap<FName, TObjectPtr<UMaterialInterface>> ExtraMaterials;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative", meta = (MultiLine = "true"))
	FString ManifestJson;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative", meta = (MultiLine = "true"))
	FString SocketsJson;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative", meta = (MultiLine = "true"))
	FString AlignmentJson;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Operative")
	FString ImportStamp;
};

/** One viseme of skeleton_and_sockets.json (`visemes`). */
struct FOperativeViseme
{
	FName Name;
	float JawOpen = 0.f;
	float Tongue = 0.f;
	TArray<TPair<int32, float>> Morphs;   // morph index, weight
	FString Phonemes;
};

/** Parses docs/animation_manifest.json and skeleton_and_sockets.json (stored in the data asset) and owns the clip table. */
UCLASS()
class MORPHRIG_API UOperativeLibrary : public UWorldSubsystem
{
	GENERATED_BODY()
public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;

	static UOperativeLibrary* Get(const UObject* WorldContext);

	bool IsReady() const { return bReady; }
	UOperativeAssets* GetAssets() const { return Assets; }
	const FOperativeClipInfo* FindClip(FName Id) const { return Clips.Find(Id); }
	FOperativeClipInfo* FindClipMutable(FName Id) { return Clips.Find(Id); }
	const TArray<FName>& GetClipOrder() const { return ClipOrder; }
	UAnimSequence* GetSequence(FName Id) const;
	float GetClipLength(FName Id) const;

	const TArray<FName>& GetMorphNames() const { return MorphNames; }
	int32 FindMorphIndex(FName Name) const;
	const TArray<FOperativeViseme>& GetVisemes() const { return Visemes; }
	const TArray<FOperativeSpeechSpan>& GetSpeechWords() const { return SpeechWords; }
	const TArray<FOperativeSpeechSpan>& GetSpeechSentences() const { return SpeechSentences; }
	int32 FindViseme(FName Name) const;

	/** Foot ankle positions in root space (cm) for pose matching. */
	bool GetFootPositions(FName ClipId, float Time, FVector& OutLeft, FVector& OutRight) const;

	/** Component space position of any bone at a clip time (walks the parent chain of the skeleton). */
	bool GetBonePositionCS(FName ClipId, FName BoneName, float Time, FVector& OutPos) const;

	/** Best cyclic phase (0..1) of a loop clip whose feet match the given reference feet (root space). */
	float MatchLoopPhase(FName ClipId, const FVector& RefLeft, const FVector& RefRight, int32 Steps = 32) const;

	/** Manifest lookups used by the runtime: returns the event list for a clip (may be empty). */
	const TArray<FOperativeEventDef>* GetEvents(FName ClipId) const;

	FString GetSummary() const;

private:
	void ParseManifest(const FString& Json);
	void ParseSockets(const FString& Json);
	void ParseAlignment(const FString& Json);
	void BuildBoneChains();

	UPROPERTY(Transient)
	TObjectPtr<UOperativeAssets> Assets;

	TMap<FName, FOperativeClipInfo> Clips;
	TArray<FName> ClipOrder;
	TArray<FName> MorphNames;
	TArray<FOperativeViseme> Visemes;
	TArray<FOperativeSpeechSpan> SpeechWords;
	TArray<FOperativeSpeechSpan> SpeechSentences;
	bool bReady = false;

	// bone chains (skeleton indices) for the foot tables: root .. foot
	TArray<int32> LeftChain;
	TArray<int32> RightChain;
	bool bChainsValid = false;
	mutable TMap<FName, TArray<int32>> BoneChainCache;
};
