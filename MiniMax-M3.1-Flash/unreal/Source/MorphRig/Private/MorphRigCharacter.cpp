// MorphRig - the playable Operative.
#include "MorphRigCharacter.h"

#include "Animation/AnimInstance.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Components/LineBatchComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/DataTable.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "MorphRigAnimInstance.h"
#include "MorphRigHUD.h"
#include "MorphRigLog.h"

// The log category is defined exactly once for the whole module.
DEFINE_LOG_CATEGORY(LogMorphRig);

static const TCHAR* MorphRigMeshPath = TEXT("/Game/MorphRig/Meshes/SK_Operative");
static const TCHAR* MorphRigAccentPath = TEXT("/Game/MorphRig/Materials/MI_M_Accent");
static const TCHAR* MorphRigNormalViewPath = TEXT("/Game/MorphRig/Materials/M_ViewNormal");
static const TCHAR* MorphRigClayViewPath = TEXT("/Game/MorphRig/Materials/M_ViewClay");
static const TCHAR* MorphRigTablePath = TEXT("/Game/MorphRig/DT_MorphRigClips");
static const TCHAR* MorphRigAnimDir = TEXT("/Game/MorphRig/Animations/");

AMorphRigCharacter::AMorphRigCharacter()
{
	PrimaryActorTick.bCanEverTick = true;

	GetCapsuleComponent()->InitCapsuleSize(34.0f, 88.0f);

	if (USkeletalMeshComponent* Mesh = GetMesh())
	{
		Mesh->SetRelativeLocation(FVector(0.0f, 0.0f, -88.0f));
		Mesh->SetRelativeRotation(FRotator::ZeroRotator);
	}

	// The camera is attached to the root and not to a spring arm: a spring
	// arm drives the camera every frame, which would fight the showcase
	// framings the UpdateCamera function sets up.
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(RootComponent);
	Camera->bUsePawnControlRotation = false;

	SkeletonLines = CreateDefaultSubobject<ULineBatchComponent>(TEXT("SkeletonLines"));
	SkeletonLines->SetupAttachment(RootComponent);
	SkeletonLines->SetVisibility(false);

	bUseControllerRotationYaw = false;
	bUseControllerRotationPitch = false;
	bUseControllerRotationRoll = false;

	UCharacterMovementComponent* Move = GetCharacterMovement();
	Move->bOrientRotationToMovement = true;
	Move->RotationRate = FRotator(0.0f, TurnRate, 0.0f);
	Move->MaxWalkSpeed = WalkSpeed;
	Move->JumpZVelocity = 420.0f;
	Move->AirControl = 0.25f;
	Move->BrakingDecelerationWalking = 2200.0f;
}

UMorphRigAnimInstance* AMorphRigCharacter::GetMorphAnimInstance() const
{
	if (USkeletalMeshComponent* Mesh = GetMesh())
	{
		return Cast<UMorphRigAnimInstance>(Mesh->GetAnimInstance());
	}
	return nullptr;
}

void AMorphRigCharacter::BeginPlay()
{
	Super::BeginPlay();

	ApplyCommandLineOptions();

	// skeletal mesh and animation instance
	if (USkeletalMeshComponent* Mesh = GetMesh())
	{
		USkeletalMesh* SkeletalMesh = LoadObject<USkeletalMesh>(nullptr, MorphRigMeshPath);
		if (SkeletalMesh)
		{
			Mesh->SetSkeletalMesh(SkeletalMesh);
		}
		Mesh->SetAnimInstanceClass(UMorphRigAnimInstance::StaticClass());
		Mesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		Mesh->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
	}

	// team accent material instance
	if (USkeletalMeshComponent* Mesh = GetMesh())
	{
		if (UMaterialInterface* Accent = LoadObject<UMaterialInterface>(nullptr, MorphRigAccentPath))
		{
			if (Mesh->GetNumMaterials() >= 8)
			{
				AccentMID = Mesh->CreateAndSetMaterialInstanceDynamic(7);
				if (AccentMID)
				{
					UMaterialInstanceDynamic* AccentDynamic =
						UMaterialInstanceDynamic::Create(Accent, this);
					if (AccentDynamic)
					{
						Mesh->SetMaterial(7, AccentDynamic);
						AccentMID = AccentDynamic;
					}
				}
			}
		}
	}

	// the two helper materials for the normal and the clay view
	NormalViewMaterial = LoadObject<UMaterialInterface>(nullptr, MorphRigNormalViewPath);
	ClayViewMaterial = LoadObject<UMaterialInterface>(nullptr, MorphRigClayViewPath);
	if (!NormalViewMaterial || !ClayViewMaterial)
	{
		UE_LOG(LogMorphRig, Warning,
			   TEXT("the view materials are missing, only the textured view works"));
	}

	BuildClipLibrary();

	if (UMorphRigAnimInstance* AI = GetMorphAnimInstance())
	{
		AI->SetTeamColor(FLinearColor(1.0f, 0.55f, 0.10f, 1.0f));
	}

	// The shading asked for on the command line is applied here, the mesh and
	// its material slots only exist from here on.
	if (!PendingMaterialView.IsEmpty())
	{
		if (PendingMaterialView == TEXT("normal"))
		{
			SetMaterialView(EMorphRigMaterialView::Normal);
		}
		else if (PendingMaterialView == TEXT("clay"))
		{
			SetMaterialView(EMorphRigMaterialView::Clay);
		}
		else
		{
			SetMaterialView(EMorphRigMaterialView::Textured);
		}
	}

	PlayClip(TEXT("idle_combat"));
}

void AMorphRigCharacter::BuildClipLibrary()
{
	ClipLibrary.Reset();
	UDataTable* Table = LoadObject<UDataTable>(nullptr, MorphRigTablePath);
	if (!Table)
	{
		UE_LOG(LogMorphRig, Warning, TEXT("clip table not found at %s"), MorphRigTablePath);
		return;
	}
	Table->ForeachRow<FMorphRigClipEntry>(TEXT("MorphRigClip"),
		[this](const FName&, const FMorphRigClipEntry& Row)
		{
			UAnimSequenceBase* Sequence =
				LoadObject<UAnimSequenceBase>(nullptr, *Row.AssetPath);
			if (Sequence)
			{
				ClipLibrary.Add(Row.ClipName, Sequence);
			}
			else
			{
				UE_LOG(LogMorphRig, Warning, TEXT("clip asset missing: %s"), *Row.AssetPath);
			}
		});
	UE_LOG(LogMorphRig, Log, TEXT("loaded %d clips"), ClipLibrary.Num());
}

TArray<FString> AMorphRigCharacter::GetAllClipNames()
{
	TArray<FString> Names;
	UDataTable* Table = LoadObject<UDataTable>(nullptr, MorphRigTablePath);
	if (!Table)
	{
		return Names;
	}
	Table->ForeachRow<FMorphRigClipEntry>(TEXT("MorphRigClip"),
		[&Names](const FName&, const FMorphRigClipEntry& Row)
		{
			Names.Add(Row.ClipName);
		});
	Names.Sort();
	return Names;
}

TArray<FString> AMorphRigCharacter::SearchClips(const FString& Filter)
{
	TArray<FString> Result;
	for (const FString& Name : GetAllClipNames())
	{
		if (Filter.IsEmpty() || Name.Contains(Filter, ESearchCase::IgnoreCase))
		{
			Result.Add(Name);
		}
	}
	return Result;
}

void AMorphRigCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);
	check(PlayerInputComponent);

	PlayerInputComponent->BindAxis(TEXT("MoveForward"), this, &AMorphRigCharacter::MoveForward);
	PlayerInputComponent->BindAxis(TEXT("MoveRight"), this, &AMorphRigCharacter::MoveRight);
	PlayerInputComponent->BindAxis(TEXT("Turn"), this, &AMorphRigCharacter::Turn);
	PlayerInputComponent->BindAxis(TEXT("LookUp"), this, &AMorphRigCharacter::LookUp);

	PlayerInputComponent->BindAction(TEXT("Jump"), IE_Pressed, this, &AMorphRigCharacter::JumpAction);
	PlayerInputComponent->BindAction(TEXT("Fire"), IE_Pressed, this, &AMorphRigCharacter::Fire);
	PlayerInputComponent->BindAction(TEXT("Secondary"), IE_Pressed, this, &AMorphRigCharacter::Secondary);
	PlayerInputComponent->BindAction(TEXT("Ability"), IE_Pressed, this, &AMorphRigCharacter::Ability);
	PlayerInputComponent->BindAction(TEXT("Dodge"), IE_Pressed, this, &AMorphRigCharacter::Dodge);
	PlayerInputComponent->BindAction(TEXT("Interact"), IE_Pressed, this, &AMorphRigCharacter::Interact);
	PlayerInputComponent->BindAction(TEXT("ToggleAim"), IE_Pressed, this, &AMorphRigCharacter::ToggleAim);
	PlayerInputComponent->BindAction(TEXT("CycleCamera"), IE_Pressed, this, &AMorphRigCharacter::CycleCamera);
	PlayerInputComponent->BindAction(TEXT("ToggleTeam"), IE_Pressed, this, &AMorphRigCharacter::ToggleTeam);
	PlayerInputComponent->BindAction(TEXT("ToggleLOD"), IE_Pressed, this, &AMorphRigCharacter::ToggleLOD);
	PlayerInputComponent->BindAction(TEXT("ToggleSkeleton"), IE_Pressed, this, &AMorphRigCharacter::ToggleSkeleton);
	PlayerInputComponent->BindAction(TEXT("ToggleMaterialView"), IE_Pressed, this, &AMorphRigCharacter::ToggleMaterialView);
	PlayerInputComponent->BindAction(TEXT("ResetChar"), IE_Pressed, this, &AMorphRigCharacter::ResetChar);
	PlayerInputComponent->BindAction(TEXT("PlaySpeech"), IE_Pressed, this, &AMorphRigCharacter::PlaySpeech);
	PlayerInputComponent->BindAction(TEXT("BrowseClips"), IE_Pressed, this, &AMorphRigCharacter::ToggleBrowser);
	PlayerInputComponent->BindAction(TEXT("Showcase"), IE_Pressed, this, &AMorphRigCharacter::RunShowcase);
	PlayerInputComponent->BindAction(TEXT("ToggleInstances"), IE_Pressed, this, &AMorphRigCharacter::ToggleInstances);

	// The animation browser filter is typed directly, one binding per key.
	static const TCHAR* GFilterKeys[] = {
		TEXT("A"), TEXT("B"), TEXT("C"), TEXT("D"), TEXT("E"), TEXT("F"), TEXT("G"),
		TEXT("H"), TEXT("I"), TEXT("J"), TEXT("K"), TEXT("L"), TEXT("M"), TEXT("N"),
		TEXT("O"), TEXT("P"), TEXT("Q"), TEXT("R"), TEXT("S"), TEXT("T"), TEXT("U"),
		TEXT("V"), TEXT("W"), TEXT("X"), TEXT("Y"), TEXT("Z")
	};
	for (const TCHAR* Key : GFilterKeys)
	{
		PlayerInputComponent->BindKey(FKey(Key), IE_Pressed, this,
			&AMorphRigCharacter::AppendFilterKey);
	}
	PlayerInputComponent->BindKey(EKeys::BackSpace, IE_Pressed, this,
		&AMorphRigCharacter::BackspaceBrowserFilter);
	PlayerInputComponent->BindKey(EKeys::Up, IE_Pressed, this,
		&AMorphRigCharacter::MoveBrowserSelectionUp);
	PlayerInputComponent->BindKey(EKeys::Down, IE_Pressed, this,
		&AMorphRigCharacter::MoveBrowserSelectionDown);
	PlayerInputComponent->BindKey(EKeys::Enter, IE_Pressed, this,
		&AMorphRigCharacter::PlaySelectedClip);
	PlayerInputComponent->BindKey(EKeys::LeftBracket, IE_Pressed, this,
		&AMorphRigCharacter::SlowerPlayback);
	PlayerInputComponent->BindKey(EKeys::RightBracket, IE_Pressed, this,
		&AMorphRigCharacter::FasterPlayback);
}

void AMorphRigCharacter::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);
	if (APlayerController* PC = Cast<APlayerController>(NewController))
	{
		PC->bShowMouseCursor = true;
	}
}

void AMorphRigCharacter::MoveForward(float Value)
{
	if (Controller && !bAiming)
	{
		const FRotator Yaw(0.0f, Controller->GetControlRotation().Yaw, 0.0f);
		AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::X), Value);
	}
}

void AMorphRigCharacter::MoveRight(float Value)
{
	if (Controller && !bAiming)
	{
		const FRotator Yaw(0.0f, Controller->GetControlRotation().Yaw, 0.0f);
		AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y), Value);
	}
}

void AMorphRigCharacter::Turn(float Value)
{
	if (Controller && !bAiming)
	{
		AddControllerYawInput(Value);
	}
}

void AMorphRigCharacter::LookUp(float Value)
{
	if (Controller)
	{
		AddControllerPitchInput(Value);
	}
}

void AMorphRigCharacter::JumpAction()
{
	if (bAiming)
	{
		return;
	}
	Jump();
	if (UMorphRigAnimInstance* AI = GetMorphAnimInstance())
	{
		AI->SetState(EMorphRigState::Jump);
		AI->ApplyBaseSequence(FindClip(TEXT("jump_start")), false);
	}
}

void AMorphRigCharacter::ToggleAim()
{
	bAiming = !bAiming;
	if (UMorphRigAnimInstance* AI = GetMorphAnimInstance())
	{
		AI->bAiming = bAiming;
	}
	UE_LOG(LogMorphRig, Log, TEXT("aim %s"), bAiming ? TEXT("on") : TEXT("off"));
}

void AMorphRigCharacter::CycleCamera()
{
	const uint8 Next = (uint8)CameraMode + 1;
	SetCameraMode((EMorphRigCameraMode)(Next % 5));
}

void AMorphRigCharacter::Fire()
{
	TriggerAction(TEXT("melee_1"));
}

void AMorphRigCharacter::Secondary()
{
	TriggerAction(TEXT("ranged_fire"));
}

void AMorphRigCharacter::Ability()
{
	TriggerAction(TEXT("cast_directional"));
}

void AMorphRigCharacter::Dodge()
{
	TriggerAction(TEXT("dash_f"));
}

void AMorphRigCharacter::Interact()
{
	TriggerAction(TEXT("deploy"));
}

void AMorphRigCharacter::ToggleTeam()
{
	const int32 Team = (TeamIndex + 1) % 2;
	SetTeam(Team);
}

void AMorphRigCharacter::ToggleLOD()
{
	SetLOD((LODIndex + 1) % 3);
}

void AMorphRigCharacter::ToggleSkeleton()
{
	SetShowSkeleton(!bShowSkeletonOverlay);
}

void AMorphRigCharacter::ResetChar()
{
	ResetCharacter();
}

void AMorphRigCharacter::PlaySpeech()
{
	PlayPerformance();
}

void AMorphRigCharacter::ToggleBrowser()
{
	ToggleAnimationBrowser();
}

void AMorphRigCharacter::RunShowcase()
{
	if (IsShowcaseRunning())
	{
		StopShowcaseSequence();
	}
	else
	{
		StartShowcaseSequence();
	}
}

void AMorphRigCharacter::ToggleInstances()
{
	ToggleInstanceCount();
}
