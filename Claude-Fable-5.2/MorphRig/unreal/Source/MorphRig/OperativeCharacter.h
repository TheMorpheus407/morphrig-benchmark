#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "OperativeStateComponent.h"
#include "OperativeCharacter.generated.h"

class UAudioComponent;
class UStaticMeshComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;

UENUM()
enum class EOpDisplayMode : uint8
{
	Textured,
	Wireframe,
	Normals,
	Clay
};

/** The Operative: capsule + skeletal mesh driven by UOperativeAnimInstance / UOperativeStateComponent, plus showcase presentation. */
UCLASS()
class MORPHRIG_API AOperativeCharacter : public ACharacter
{
	GENERATED_BODY()
public:
	AOperativeCharacter(const FObjectInitializer& ObjectInitializer);

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaTime) override;
	virtual void Landed(const FHitResult& Hit) override;

	UPROPERTY(VisibleAnywhere, Category = "MorphRig")
	TObjectPtr<UOperativeStateComponent> StateComp;
	UPROPERTY(VisibleAnywhere, Category = "MorphRig")
	TObjectPtr<UAudioComponent> Voice;
	UPROPERTY(VisibleAnywhere, Category = "MorphRig")
	TObjectPtr<UStaticMeshComponent> TeamRing;
	UPROPERTY(VisibleAnywhere, Category = "MorphRig")
	TObjectPtr<UStaticMeshComponent> BladeGlow;

	int32 InstanceIndex = 0;
	FVector SpawnLocation = FVector::ZeroVector;
	float SpawnYaw = 0.f;
	FVector ViewerLocation = FVector::ZeroVector;
	FVector HeadForwardLocal = FVector(0, 0, 1);

	// ---- presentation
	void SetTeam(int32 InTeam);
	int32 GetTeam() const { return Team; }
	void SetOutline(bool bOn);
	bool HasOutline() const { return bOutline; }
	void SetRing(bool bOn);
	bool HasRing() const { return bRing; }
	void SetDisplayMode(EOpDisplayMode Mode);
	EOpDisplayMode GetDisplayMode() const { return DisplayMode; }
	void SetLodMode(int32 Mode);            // 0 = automatic, 1..3 = forced LOD0..LOD2
	int32 GetLodMode() const { return LodMode; }
	int32 GetCurrentLod() const;
	void SetMeshHiddenForBlink(bool bHidden);
	void PulseHitFlash() { HitFlash = 1.f; }
	void OnRespawned();
	void PlayDialogueAudio(float StartTime);
	void StopDialogueAudio();
	bool IsDialogueAudioPlaying() const;
	FLinearColor GetTeamColor() const;
	float GetContactError(FName& OutProp, FName& OutHolder) const;

	// ---- autopilot for the extra instances
	bool bAutopilot = false;
	FVector AutopilotCenter = FVector::ZeroVector;

private:
	void ApplyMaterials();
	void HandleEvent(UOperativeStateComponent* Comp, const FOpClipPlay& Play, FName Event);
	void UpdateEffects(float Dt);
	void TickAutopilot(float Dt);

	UPROPERTY(Transient)
	TArray<TObjectPtr<UMaterialInstanceDynamic>> SlotMids;
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> OutlineMid;
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> RingMid;
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> BladeMid;
	UPROPERTY(Transient)
	TObjectPtr<AActor> WorldBeacon;

	int32 Team = 0;
	bool bOutline = false;
	bool bRing = true;
	EOpDisplayMode DisplayMode = EOpDisplayMode::Textured;
	int32 LodMode = 0;
	float HitFlash = 0.f;
	float Dissolve = 0.f;
	float DissolveTarget = 0.f;
	float DissolveSpeed = 4.f;
	bool bHiddenForBlink = false;
	float AutoTime = 0.f;
	int32 AutoStep = -1;
};
